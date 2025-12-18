import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from openai import OpenAI

MODEL_STAGE_1 = os.getenv("MODEL_STAGE_1", "gemini-3-pro-preview")
MODEL_STAGE_2 = os.getenv("MODEL_STAGE_2", "gpt-51-1113-global")
MODEL_STAGE_3 = os.getenv("MODEL_STAGE_3", "gemini-3-pro-preview")
MODEL_SUM = os.getenv("MODEL_SUM", os.getenv("MODEL_STAGE_SUM", "gpt-51-1113-global"))
MODEL_SOLVE = os.getenv("MODEL_SOLVE", "gemini-3-pro-preview")
MODEL_ANALYSIS = os.getenv("MODEL_ANALYSIS", "gpt-51-1113-global")

API_BASE_URL = "https://idealab.alibaba-inc.com/api/openai/v1"
API_KEY = "e086b5a947c3c2651165617b22318df5"

MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "5"))
QUESTION_LOG_PATH = os.getenv("QUESTION_LOG_PATH", "question_log.jsonl")


@dataclass
class StageResult:
    question: str
    answer: str
    raw: str


def encode_image(image_path: Path) -> str:
    with image_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vision_model(prompt: str, image_path: Path, model: str) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    base64_image = encode_image(image_path)

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ],
    )
    return resp.choices[0].message.content


def call_text_model(prompt: str, model: str) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def extract_tag(content: str, tag: str) -> str:
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = content.find(start_tag)
    end = content.find(end_tag)
    if start == -1 or end == -1:
        raise ValueError(f"响应中缺少 {start_tag} 或 {end_tag} 标签: {content}")
    return content[start + len(start_tag) : end].strip()


def parse_option_letter(text: str) -> str:
    match = re.search(r"[A-D]", text)
    if not match:
        raise ValueError(f"未能解析选项字母: {text}")
    return match.group(0)


def run_stage(prompt: str, image_path: Path, model: str) -> StageResult:
    raw = call_vision_model(prompt, image_path, model)
    return StageResult(
        question=extract_tag(raw, "question"),
        answer=extract_tag(raw, "answer"),
        raw=raw,
    )


def save_round_questions(
    log_path: Path,
    round_idx: int,
    stage_one: StageResult,
    stage_two: StageResult,
    stage_three: StageResult,
    stage_final: StageResult,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "round": round_idx,
        "stage_1": {
            "question": stage_one.question,
            "answer": stage_one.answer,
            "raw": stage_one.raw,
        },
        "stage_2": {
            "question": stage_two.question,
            "answer": stage_two.answer,
            "raw": stage_two.raw,
        },
        "stage_3": {
            "question": stage_three.question,
            "answer": stage_three.answer,
            "raw": stage_three.raw,
        },
        "stage_final": {
            "question": stage_final.question,
            "answer": stage_final.answer,
            "raw": stage_final.raw,
        },
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def build_initial_prompt(context: str, feedback: str, previous_question: str | None) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    previous = f"\n上一轮最终问题: {previous_question.strip()}" if previous_question else ""
    return dedent(
        f"""
        你需要围绕图片“中心区域”的视觉要素设计一个高难度的单选题（MCQ）。
        请在上一轮最终问题的基础上进行升级或变形，保持题干可由图片与文档推导得到。
        步骤:
        1) 先描述图片中央最关键的结构/现象，并指出它与整体的关系。
        2) 基于该视觉锚点提出题干，题干必须包含 A-D 四个选项。
        3) 正确答案需要在下述文档内容中找到依据，同时必须依赖图片理解而非纯文本记忆。
        {extra}{previous}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_revision_prompt(context: str, first: StageResult, feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    return dedent(
        f"""
        这是第一步生成的问题与答案:
        问题: {first.question}
        答案: {first.answer}

        请继续围绕图片中心视觉锚点，增加一层额外推理，生成更难的单选题:
        - 新题需要在题干中显式提到第一次题目的视觉锚点，然后引入文档中的另一个关键要点形成因果/对比关系。
        - 题干必须包含 A-D 选项，且答案可在文档中找到确切依据。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_third_prompt(context: str, second: StageResult, feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    return dedent(
        f"""
        这是第二步生成的问题与答案:
        问题: {second.question}
        答案: {second.answer}
        {extra}

        请继续围绕图片中心视觉锚点，增加一层额外推理，生成更难的单选题:
        - 新题需要在题干中显式提到第二步题目的视觉锚点，然后引入文档中的另一个关键要点形成因果/对比关系。
        - 题干必须包含 A-D 选项，且答案可在文档中找到确切依据。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_final_prompt(
    context: str, first: StageResult, second: StageResult, third: StageResult, feedback: str
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    return dedent(
        f"""
        你需要把前三步的逻辑链路整合成一个“多步推理”的高难度单选题（MCQ），
        要求回答必须先识别图片中心视觉信息，再结合文档内容得出答案。

        前三步结果:
        1) 问题: {first.question}
           答案: {first.answer}
        2) 问题: {second.question}
           答案: {second.answer}
        3) 问题: {third.question}
           答案: {third.answer}
        {extra}

        生成新题的要求:
        - 题干引导考生先定位图片中央的关键结构，再利用文档信息完成多步推理。
        - 选项 A-D 需要设置迷惑项，只有经过多步推理才能排除。
        - 答案需要在文档中找到依据，但必须依赖图片中心信息才能确认。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_solver_prompt(context: str, question: str) -> str:
    return dedent(
        f"""
        你是一名考生，请结合图片和文档作答单选题。仅输出选项字母 (A/B/C/D)。

        题目:
        {question}

        文档:
        {context.strip()}
        """
    ).strip()


def build_analysis_prompt(question: str, answer: str, solver_answer: str) -> str:
    return dedent(
        f"""
        下述单选题已被求解模型答出，请总结题目为何仍然简单，并给出提高难度的3条建议。
        题目: {question}
        标准答案: {answer}
        求解模型作答: {solver_answer}

        输出格式:
        - 用简洁中文列出3条提高难度的指引。
        - 不要重复题面原句。
        """
    ).strip()


def generate_questions(
    context: str, image_path: Path, feedback: str, previous_final_question: str | None
) -> tuple[StageResult, StageResult, StageResult, StageResult]:
    stage_one = run_stage(
        build_initial_prompt(context, feedback, previous_final_question),
        image_path,
        MODEL_STAGE_1,
    )
    print("第一次生成:", stage_one.raw)

    stage_two = run_stage(build_revision_prompt(context, stage_one, feedback), image_path, MODEL_STAGE_2)
    print("第二次生成:", stage_two.raw)

    stage_three = run_stage(build_third_prompt(context, stage_two, feedback), image_path, MODEL_STAGE_3)
    print("第三次生成:", stage_three.raw)

    stage_final = run_stage(
        build_final_prompt(context, stage_one, stage_two, stage_three, feedback),
        image_path,
        MODEL_SUM,
    )
    print("最终合并生成:", stage_final.raw)

    return stage_one, stage_two, stage_three, stage_final


def try_solve_question(context: str, question: str, image_path: Path) -> tuple[str, str]:
    solver_prompt = build_solver_prompt(context, question)
    solver_raw = call_vision_model(solver_prompt, image_path, MODEL_SOLVE)
    solver_letter = parse_option_letter(solver_raw)
    print("求解模型回答:", solver_raw)
    return solver_raw, solver_letter


def main() -> None:
    image_path = Path("test.png")
    if not image_path.exists():
        raise FileNotFoundError(f"未找到图片文件: {image_path}")

    context = dedent(
        """
        Rb Doping and Lattice Strain Synergistically Engineering Oxygen Vacancies in TiO2 for Stable High-Contrast Photoreversible Color Switching

Xiangyu Tian, Zixu Zeng, Yi He, Lecheng Lei, Chunlin Yu, and Xingwang Zhang*

Abstract:
The utilization of $TiO_{2}$ for the fabrication of transparent photochromic materials is both cost-effective and environmentally friendly. However, it still poses challenges due to the rapid recombination of electron-hole pairs and poor organic-inorganic compatibility. Oxygen vacancies play a crucial role in sustaining sacrificial electron donors for hole scavenging, demonstrating great potential in enhancing photochromic performance. Herein, Rb doping and lattice strain are applied to synergistically engineer oxygen vacancies, considering lattice oxygen release is influenced by charge neutrality and oxygen atom coordination environment. Furthermore, the particle surface is modified using composite siloxanes to ensure monodispersion and enhance organic-inorganic compatibility. Structural analyses and theoretical calculations indicate that Rb doping and epitaxial strain synergistically reduce the oxygen vacancy formation energy and promote the chemical adsorption of diethylene glycol (DEG) on the $TiO_{2}$ surface for hole scavenging. The designed DEG-added $Rb-TiO_{2}/TB-CS$ (TB means extra titanium butoxide, CS means composite siloxanes) nanodispersion exhibits a significant optical modulation amplitude exceeding 90% at 650 nm, rapid response within 60 s, and stable reversibility in color-switching (50 cycles). Moreover, utilizing $Rb-TiO_{2}/TB-CS$ with DEG ligands as a responsive material enables the fabrication of transparent photochromic polyacrylate-based hybrid films, polyvinyl alcohol-based hydrogels, and hydroxyethyl cellulose-based rewritable papers, showcasing its immense potential for diverse applications.

1. Introduction

The utilization of photochromic materials capable of reversible color switching in response to external light stimuli has played a pivotal role across various fields, including optical displays, sensors, and data storage. Furthermore, imparting transparency properties to these materials opens up new avenues for numerous applications such as smart windows, transparent displays, and wearable devices. However, the fabrication of transparent photochromic materials that demonstrate significant optical modulation amplitude, rapid response, and stable color-switching reversibility remains a challenge from both a technical and economic standpoint. Although organic photochromic molecules have undergone extensive development, the majority still necessitate intricate synthesis procedures and toxic precursors and exhibit unstable physicochemical properties. In contrast, photochromic transition metal oxides have higher thermal stability, chemical resistance, and strength. Titanium dioxide ($TiO_{2}$) is considered a promising functional component for photochromic materials due to its abundant elemental reserve, nontoxic nature, and physicochemical stability. In recent years, photochromic systems incorporating $TiO_{2}$ and redox dyes such as methylene blue (MB) have been developed to achieve reversible color switching through the reduction of dyes by photogenerated electrons and oxidation of dyes by oxidant. However, such systems still suffer from low transparency, potential toxicity risks, and limited ability for reversible color-switching due to photocatalytic degradation of the dyes.

Constructing reversible photochromic systems in which $TiO_{2}$ itself functions as the color-changing component is anticipated to address the aforementioned issues. To achieve high transparency of the composite materials, it is necessary for the particle size of $TiO_{2}$ to be less than 40 nm (one-tenth of the minimum wavelength of visible light). Additionally, a sufficiently elevated concentration of $TiO_{2}$ within the polymer matrix is required to ensure large optical modulation amplitude (high contrast). Therefore, surface modification becomes imperative to guarantee particle monodispersity and enhance organic-inorganic compatibility for the prevention of Rayleigh scattering. In these systems, the redox between Ti(IV) and Ti(III) driven by photoinduced electrons and oxygen enables reversible color switching between white and dark blue. Fundamentally, the performance of photochromism, including response speed and optical modulation amplitude, critically relies on the efficient scavenging of photoinduced holes, which allows photoinduced electrons to escape recombination and reduce Ti(IV).

Notably, oxygen vacancies with localized electrons play a key role in hole scavenging. On one hand, it has been reported that oxygen vacancies directly act as sacrificial electron donors (SEDs) to capture photoinduced holes. On the other hand, oxygen vacancies can serve as reaction sites for the dissociation of organic adsorbates. Chemisorbed alcohol ligands on $TiO_{2}$ surfaces have been proven to function as SEDs to scavenge holes. Thus, the photochromic performance can be substantially enhanced through oxygen vacancies engineering, while ensuring the preservation of surface groups crucial for subsequent modification and application. To modulate the electronic structure for facilitating the generation of oxygen vacancies, it is preferable to introduce low-valent metal ions as dopants into $TiO_{2}$ in order to reduce the energy required for oxygen vacancy formation, which is induced by the retention of charge neutrality. Furthermore, the formation of oxygen vacancies, which is influenced by the coordination environment of the oxygen atoms, is associated with lattice expansion resulting from electron localization on neighboring cations. Lattice strain has been demonstrated to distort local bonding and impact the ligand field. Additionally, tensile strain is considered to decrease the migration barrier for oxygen atom transfer and surface exchange, indicating a strong correlation between lattice strain and oxygen defect chemistry. Therefore, doping low-valent metal ions and engineering lattice strain may synergistically reduce the oxygen vacancy formation energy, thereby promoting the abundant generation of oxygen vacancies in $TiO_{2}$.

Herein, we present a novel $Rb-TiO_{2}/TB-CS$ photochromic responsive structure for the construction of reversible photochromic systems. The synergistic strategy of rubidium (Rb) doping and lattice strain greatly facilitates the generation of oxygen vacancies and enhances the chemical adsorption of DEG molecules on the $TiO_{2}$ surface, which efficiently acts as SEDs to scavenge holes. Additionally, surface modification using composite siloxanes ensures the monodispersion of nanoparticles and improves organic-inorganic compatibility. The $Rb-TiO_{2}/TB-CS$ nanodispersion, with the addition of DEG, exhibits high transparency and can undergo rapid coloration from clear to dark blue in tens of seconds under UV irradiation. Moreover, it conveniently fades through air oxidation. Notably, this nanodispersion demonstrates an ultrahigh optical modulation amplitude exceeding 90% at 650 nm and enhanced color-switching reversibility (50 cycles) compared to previous studies. The polyacrylate-based transparent photochromic hybrid film, fabricated with $Rb-TiO_{2}/TB-CS$ and possessing excellent flexibility, exhibits a high optical contrast of 82.74% at 650 nm in photochromic process and can be photo-printed with complex patterns and texts in high resolution. Additionally, by utilizing $Rb-TiO_{2}/TB-CS$ with DEG ligands, polyvinyl alcohol (PVA)-based transparent photochromic hydrogels and hydroxyethyl cellulose (HEC)-based rewritable papers can also be prepared. In summary, compared with published work, the $Rb-TiO_{2}/TB-CS$ as an exceptional photochromic structure possesses high transparency, superior optical modulation amplitude, enhanced color-switching reversibility, and adaptability to various systems, enabling diverse applications such as photochromic windows, transparent displays, wearable devices, and temporary data storage.

2. Result and Discussion

2.1. Preparation and Characterization of Rb-TiO2/TB-CS Structure

The fabrication of the $Rb-TiO_{2}/TB-CS$ structure is schematically illustrated in Figure 1a. The Rb-doped $TiO_{2}$ was prepared by the first solvothermal process. Subsequently, the crystalline-amorphous interface was constructed to induce lattice strain during the second solvothermal process with the extra addition of titanium butoxide (TBOT). Surface modification was performed using composite siloxanes of 3,3-dimethoxy-2,7,10,13,16-pentaoxa-3-silaheptadecane (DPSi) and 3-(acryloyloxy)propyltrimethoxysilane (APSi) to enable monodispersity of the nanoparticles (NPs) in polar solvents and provide cross-linking sites for hybridization, respectively. Pre-experiments were used to optimize the structure and guide the following investigations. The microscopic state of modified $Rb-TiO_{2}-CS$ with various feeding molar ratios of Rb/Ti (2%, 5%, 10%, and 20%) was presented in Figure S1 (Supporting Information). With increasing Rb doping levels, $Rb-TiO_{2}-CS$ NPs gradually grow and agglomerate. The heteroatoms are more inclined to be enriched in the shallow surface region of the particles. As the dopant concentration increases, defects and heteroatom sites accommodated in $TiO_{2}$ crystals become saturated, causing rubidium oxides to precipitate on the $TiO_{2}$ surface, leading to the aggregation of neighboring particles through bridging interactions. Based on the above results, the feeding ratio of Rb/Ti is determined to be 5%. It should be mentioned that $Rb-TiO_{2}-CS$ exhibits an unstable dispersion after 24 h, which makes it unsuitable for comparison in further characterizations and performance tests. The morphology of $TiO_{2}/TB-CS$ with different TBOT additions in the second solvothermal process was also investigated. As the amount of the second addition of TBOT increases, the particles crosslink with each other through amorphous structure and the boundaries become blurred, so the amount of second TBOT addition is determined to be 20% of the first TBOT addition. The sample prepared according to the optimal conditions of the pre-experiments is denoted as $Rb-TiO_{2}/TB-CS$. The transmission electron microscopy (TEM) image shown in Figure 1b displays the monodispersion and narrow size distribution of the $Rb-TiO_{2}/TB-CS$ NPs. Compared to agglomerated $Rb-TiO_{2}/TB$ NPs without modification, the $Rb-TiO_{2}/TB-CS$ NPs are uniformly monodispersed and exhibit an average particle size of 10.5 nm.

Figure 1c illustrates the epitaxial strain at the crystalline-amorphous interface mediated by the uneven volumetric shrinkage during the solvothermal process. The high-resolution TEM images of $Rb-TiO_{2}/TB-CS$ shown in Figure 1d,e demonstrate the construction of the crystalline-amorphous interface, which is formed through the in situ growth of amorphous structure on the well-crystallized $Rb-TiO_{2}$. For $Rb-TiO_{2}/TB-CS$, the lattice spacing of 1.95 Å corresponds to the (200) plane, and the lattice spacing of 3.59 Å belongs to the (101) plane. Compared to the lattice spacing of 1.90 Å (200) and 3.51 Å (101) for pure $TiO_{2}$, the increased lattice spacing of $Rb-TiO_{2}/TB-CS$ indicates the successful doping of Rb, and the increased lattice spacing of $Rb-TiO_{2}$ displayed in Figure S7 also supports it. To avoid the interference of surface modifiers on the interfacial lattice strain, the unmodified $TiO_{2}/TB$ and $Rb-TiO_{2}/TB$ are characterized by high-resolution TEM in Figure 1f,h, respectively, in which the crystalline-amorphous interfaces both are clearly visible. Geometric phase analysis (GPA) is a widely used technique that relies on the spatial transformation of crystal phases for the analysis of TEM images. GPA is based on electron diffraction theory for phase deconvolution, which is effective for investigating local lattice strains, distortions, and defects. To quantitatively investigate the distribution of strain, GPA is performed to analyze the high-resolution TEM images of unmodified $TiO_{2}/TB$ and $Rb-TiO_{2}/TB$. The results of GPA in Figure 1g,i both demonstrate that the clear axial tensile strain ($\epsilon_{yy}$) is distributed along the crystalline-amorphous interfaces in $TiO_{2}/TB$ and $Rb-TiO_{2}/TB$, which should be caused by the difference of volumetric shrinkage between crystalline and amorphous solid. Furthermore, the homogeneous distributions of Ti, O, Rb, and Si elements in $Rb-TiO_{2}/TB-CS$ are confirmed by the elemental mappings in Figure 1j. The practical Rb/Ti ratios in $Rb-TiO_{2}/TB-CS$ measured by the energy-dispersive spectrometer (EDS) and inductively coupled plasma optical emission spectrometry (ICP-OES) both are close to 2%. However, this is different from the feeding ratio of 5%, which may be explained by the fact that only part of the $Rb^{+}$ ions are successfully doped into $TiO_{2}$ due to the large radius of $Rb^{+}$ ions. Moreover, from the elemental maps for $Rb-TiO_{2}/TB-CS$ with a higher Rb/Ti feeding ratio of 10% shown in Figure S9, it can be seen that the Rb element is uniformly distributed without significant aggregation, indicating that Rb can be uniformly doped during the synthesis rather than tending to generate rubidium oxides.

To further investigate the crystalline structure, the X-ray diffraction (XRD) patterns are presented in Figure 2a. All diffraction peaks of samples correspond to those of the anatase $TiO_{2}$ phase according to JCPDS No. 21-1272. It is noteworthy that the diffraction peak of the (004) plane shifts negatively as the Rb/Ti feeding ratio increases, which indicates that $Rb^{+}$ ions with a larger ionic radius are successfully doped into the lattice of $TiO_{2}$. The size distributions of nanodispersions reflect the actual state of the NPs. Figure 2b displays the number distribution of particle size for $TiO_{2}-CS$, $TiO_{2}/TB-CS$, $Rb-TiO_{2}/TB-CS$, and unmodified $Rb-TiO_{2}/TB$ in propylene glycol monomethyl ether acetate (PGMEA). Compared to unmodified $Rb-TiO_{2}/TB$ with an average size of 295 nm, the $Rb-TiO_{2}/TB-CS$ exhibits an average size of 11.7 nm, which is roughly consistent with the statistics of the TEM, suggesting the monodispersion of $Rb-TiO_{2}/TB-CS$ NPs in PGMEA. In addition, although the particle size of $Rb-TiO_{2}/TB-CS$ is slightly increased in comparison to $TiO_{2}-CS$ and $TiO_{2}/TB-CS$, it is sufficiently smaller than 40 nm to prevent Rayleigh scattering of visible light. Furthermore, the light absorption of samples in unexcited states directly affects the transparency and photochromic contrast of the hybrid materials. The UV-vis diffuse reflectance spectra (DRS) shown in Figure 2c indicate that the $Rb-TiO_{2}/TB$ shows almost no absorption in the 600–800 nm region and exhibits a slightly increasing absorption in the 400–600 nm region in contrast to $TiO_{2}$ and $TiO_{2}/TB$, which may be due to the precipitation of rubidium oxides on the surface.

The X-ray photoelectron spectroscopy (XPS) was utilized to explore the chemical environment and electronic interactions of $Rb-TiO_{2}/TB$. All binding energy signals were calibrated with the C 1s peak at 284.8 eV. The survey XPS spectra shown in Figure 2d demonstrate the existence of Ti, Rb, O, and C elements in $Rb-TiO_{2}/TB$. The Rb 3d spectrum of $Rb-TiO_{2}/TB$ confirms the $Rb^{+}$ chemical state. In the high-resolution O 1s spectra (Figure 2e), the peak at 529.81 eV is attributed to the lattice oxygen, and the peak at 531.26 eV is assigned to the surface -OH groups. Moreover, the higher binding energy peak of O 1s can be directly related to oxygen vacancies or surface defects. Based on the changing trend of the peak area at 531.26 eV, it can be inferred that lattice strain and Rb doping facilitate the formation of more oxygen vacancies, providing $Rb-TiO_{2}/TB$ with the most oxygen defects. Figure 2f presents the high-resolution Ti 2p spectra. For $TiO_{2}$ and $TiO_{2}/TB$, the peaks at 458.59 and 464.26 eV are attributed to Ti $2p_{3/2}$ and Ti $2p_{1/2}$, respectively. Intriguingly, the binding energies of Ti $2p_{3/2}$ and Ti $2p_{1/2}$ for $Rb-TiO_{2}/TB$ shift positively by 0.17 and 0.11 eV, respectively. This may be explained that Rb only provides one valence electron and the strong electronegativity of O still contributes to maintaining the electron density on O, which further reduces the electron density on Ti, confirming the modulation of Rb doping on the electronic structure.

To further understand the structure of $Rb-TiO_{2}/TB$, the Raman spectroscopy study was carried out. As shown in Figure 2g, all Raman spectra show the characteristic Raman bands of the anatase $TiO_{2}$ phase with the strongest $E_g$ band. The $E_g$ band of $TiO_{2}/TB$ (150.5 cm$^{-1}$) exhibits a shift toward higher wavenumbers compared to that of pure $TiO_{2}$ (143.7 cm$^{-1}$), and the $E_g$ band of $Rb-TiO_{2}/TB$ is further shifted to 152.5 cm$^{-1}$. According to previous studies, the blue shift of the Raman peak is characteristic of non-stoichiometric $TiO_{2}$ and represents the disruption of lattice periodicity and octahedral symmetry, which is directly related to surface oxygen defects. This may indicate that tensile strain promotes the formation of oxygen vacancies, which is further facilitated by Rb doping through synergistic effects. The electron paramagnetic resonance (EPR) spectra used to further elucidate the presence of oxygen vacancies are displayed in Figure 2h. It is known that the EPR signal at g = 2.003 is attributed to electron-trapped oxygen vacancies. $Rb-TiO_{2}/TB$ exhibits the strongest EPR signal followed by $TiO_{2}/TB$, and $TiO_{2}$ shows the weakest EPR signal, which is consistent with the ordering of their oxygen vacancy abundances. The cyclic voltammetry (CV) measurement was also performed to visually compare the concentration of oxygen vacancies. As shown in Figure 2i and Figure S11, the larger oxidation peak area indicates a greater number of oxygen vacancies. In agreement with the results of Raman and EPR characterizations, the oxygen vacancies concentration is ranked as: $Rb-TiO_{2}/TB > TiO_{2}/TB > TiO_{2}$. The above results corroborate with each other, strongly demonstrating the synergistic promotion by tensile strain and Rb doping for the formation of oxygen vacancies.

2.2. Photochromism Performance Evaluation

Previous studies have revealed two mechanisms of oxygen vacancies in hole scavenging: oxygen vacancies possessing localized electrons that may directly serve as SEDs, and alcohols dissociatively adsorbed at oxygen vacancy sites on the surface can also act as SEDs. However, when we subjected the $Rb-TiO_{2}/TB-CS$ PGMEA nanodispersions with and without the addition of DEG under UV irradiation, DEG-added nanodispersion showed a much more intense dark blue color than the DEG-unadded nanodispersions (Figure S12). This suggests that chemisorbed DEG is more effective in scavenging holes than oxygen vacancies themselves. Additionally, compared to other polyols, DEG exhibits a stronger hole scavenging ability and stability, thereby making it the sacrificial electron donor in our system (Figure S13). Furthermore, the number of oxygen defect sites has been reported to directly affect the number of surface chemisorbed alcohols. To confirm this idea, the FT-IR spectra of samples, which were initially unmodified and were submerged in DEG under UV irradiation followed by multiple washes and centrifugation, are shown in Figure 3a. It can be seen that the abundance of oxygen vacancies in samples is positively correlated with the intensity of the peaks assigned to DEG, suggesting that oxygen vacancies act as reaction sites to promote the dissociative adsorption of DEG. In addition, compared to unmodified $Rb-TiO_{2}/TB$, peaks of the corresponding modifiers (APSi and DPSi) appear on the spectrum of $Rb-TiO_{2}/TB-CS$, indicating successful surface modification.

The DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion (volume ratio, PGMEA:DEG = 4:1) before and after UV irradiation was subjected to EPR analysis (Figure 3b). It can be seen that a clear signal appears at g = 1.941 after UV irradiation, which is attributed to $Ti^{3+}$. This confirms that the $Ti^{4+}$ is reduced to $Ti^{3+}$ by photogenerated electrons after the scavenging of holes during the photochromism process. In addition, there is still a signal of oxygen vacancies appearing after UV irradiation, which further suggests that oxygen vacancies are difficult to act as SEDs directly. To further understand the coloration mechanism of photochromism, Figure 3c shows the optical absorption of DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion before and after UV irradiation. The DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion without UV irradiation almost shows no absorption in visible and near-infrared regions, exhibiting excellent transparency. Notably, the DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion after UV irradiation exhibits a distinct dark blue color and shows increased optical absorption from visible to near-infrared region. The absorption in the visible region is attributed to the formation of $Ti^{3+}$ by the reduction of photogenerated electrons, while most of the photogenerated electrons remain as free carriers which may cause localized surface plasmon resonance (LSPR) leading to the absorption in the near-infrared region. As shown in the inset of Figure 3b, there are two explanations for the coloration caused by $Ti^{3+}$. On the one hand, $Ti^{3+}$ introduces intermediate energy levels in the bandgap of $TiO_{2}$, leading to the absorption of visible and partial near-infrared light. On the other hand, density functional theory (DFT) calculations combined with two-photon photoemission spectroscopy (2PPE) have revealed that the 3d orbitals of $Ti^{3+}$ are split into a wide occupied band gap state and an empty excited state by Jahn-Teller induced splitting. The d-d transitions from the wide occupied state to the excited state enhance the absorption in the visible region. Therefore, the extended visible absorption and near-infrared absorption together result in an absorption minimum in the blue region, which explains the dark blue color of the samples.

Figure 3d displays the schematic illustration of the color-switching mechanism of DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion. Electrons and holes are produced by UV excitation. For physisorbed DEG on the particle surface, hole scavenging involves two processes: the trapping of the hole (step 1, ≈fs) and the abstraction of hydrogen from physisorbed DEG (step 2, ≈ns). The hole is first trapped by the lattice oxygen to form the $Ti^{4+}-O\cdot$ radical, while the abstraction of hydrogen from DEG by that radical is too slow to compete with the recombination of electron-hole pairs (step 5, ≈ps). Hence, the physisorbed DEG can hardly serve as an effective SED to scavenge holes. For dissociatively adsorbed DEG, the hole can be directly trapped in a 2p orbital by the bridging oxygen (step 4, ≈fs), and a fast deprotonation process is performed to form a relatively stable ketyl radical $Ti^{4+}-O-CH-R$. Due to the faster hole scavenging than recombination of carriers, the electron can be localized on $Ti^{4+}$ to form $Ti^{3+}$ (step 3), allowing for the coloration of photochromism. The decoloration is carried out by the oxidation of $O_{2}$. Detailed mechanistic equations are presented in supporting information.

The color-switching performance and reversible stability of DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion are further investigated. The mass fraction of $Rb-TiO_{2}/TB-CS$ in the nanodispersion (volume ratio, PGMEA:DEG = 4:1) is 9.2%. As shown in Figure 3e, the transmittance of the nanodispersion gradually decreases with the increasing time of UV irradiation and reaches the minimum in 60 s, indicating the rapid response of this photochromism system. Notably, a large optical modulation amplitude is displayed, which is as high as 91.54% at 650 nm. The photochromism performance of the nanodispersion under sunlight is also investigated. The transmittance of the nanodispersion decreases with the increasing sunlight exposure time and gradually approaches the minimum after 150 min. The optical modulation amplitude is measured to be 79.5% at 650 nm, and the nanodispersion still can present clear photochromic color switching. Figure 3f shows the transmittance of this system during the decoloration process in air. The transmittance of colored nanodispersion increases with the gradual oxidation of $Ti^{3+}$ by oxygen and recovers to its initial state after 120 min. The physical adsorption layer of DEG on the particle surface may stabilize the coloring state by blocking $O_{2}$. In addition, rapid decoloration in seconds can be achieved by injecting air directly into the nanodispersion repeatedly.

The color-switching reversibility of three samples is compared in Figure 3g. The initial response time is used as the UV irradiation time in color-switching cycle tests. DEG-added $TiO_{2}-CS$ and $TiO_{2}/TB-CS$ nanodispersions exhibit optical modulation amplitudes less than 70% after 21 and 35 color-switching cycles, respectively. The hole scavenging rate is positively correlated with the number of DEG chemisorbed on the particle surface. It can be found that the initial optical modulation amplitude of $Rb-TiO_{2}/TB-CS$ is higher than others in the same irradiation time. Furthermore, the abundant oxygen vacancies of $Rb-TiO_{2}/TB-CS$ enable the nanodispersion stable color-switching reversibility, whose optical modulation amplitude is still more than 80% after 50 cycles. These results demonstrate oxygen vacancies engineering significantly enhances the photochromic performance including optical modulation amplitude, response speed, and color-switching reversibility. The reduction in photochromic performance after multiple cycles may be caused by the inactivation of a minor part of oxygen vacancies. The inactivation of oxygen vacancies is attributed to the adsorption and dissociation of $O_{2}$ and the dissociative adsorption of $H_{2}O$ to form surface hydroxyl groups. The EPR spectra of DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion before and after 50 color-switching cycles display that the intensity of the signal belonged to oxygen vacancy is slightly decreased after 50 cycles, demonstrating the consumption of oxygen vacancies in photoreversible color-switching process.

Furthermore, to study the long-term stable color-switching performance of $Rb-TiO_{2}/TB-CS$, the changes in morphology and surface structure before and after the color-switching cycle test deserve further investigation. $Rb-TiO_{2}/TB-CS$ from DEG-added nanodispersion exhibits no apparent change in the morphology and grain structure after 50 color-switching cycles. It cannot be ignored that although the slow electron injection leads to the inhibition of the decomposition of the keto radical $Ti^{4+}-O\cdot-CH-R$ to form R-CHO due to the breaking of the strong Ti-O bond, the DEG may decompose after scavenging holes in the color-switching cycles. The analysis based on the XPS spectra of C 1s demonstrates that the partial DEG ligand undergoes decomposition after scavenging holes and new DEG molecules would be liganded to the particle surface. Sufficient DEG in the solvent environment ensures a long-term supply of sacrificial electron donors on the particle surface to counteract the decomposition of DEG. The thermogravimetric analysis (TGA) of DEG-liganded $Rb-TiO_{2}/TB$ nanoparticles is performed to determine the surface content of chemisorbed DEG, and the coverage of the DEG before and after 50 color-switching cycles is calculated to be 5.76 and 5.19 nm$^{-2}$, respectively. Since DEG is added in excess in the system, the decrease in chemisorbed DEG content should be attributed to the depletion of oxygen vacancies. Moreover, a longer test of 150 color-switching cycles is used to verify the long-term reversibility of $Rb-TiO_{2}/TB-CS$ from DEG-added nanodispersion. The $Rb-TiO_{2}/TB-CS$ exhibits relatively stable reversibility in long-term color switching and the optical modulation amplitude at 650 nm gradually stabilizes at ≈65% over 150 color-switching cycles. It is still enough to perform a clear photochromic contrast and the dark blue color (high optical modulation amplitude) can be obtained by increasing the UV irradiation time. In summary, the number of oxygen vacancies determines the long-term stability of the system and can reach a steady state in 150 color-switching cycles, which may be attributed to the synergistic effect of Rb doping and lattice strain on balancing oxygen vacancies.

Due to the variety of environmental conditions in practical applications, it is essential to study the performance and stability of materials under different conditions. The optical modulation amplitude, response time, and color-switching reversibility of DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion at different temperatures, humidities, and UV light intensities are further studied. Temperature has little effect on optical modulation amplitude and color-switching reversibility, but higher temperature significantly accelerates the oxidation of $Ti^{3+}$, thereby shortening the recovery time. Humidity only exhibits an effect on color-switching reversibility. With increasing humidity, the color-switching reversibility weakens, which is attributed to the increased dissociative adsorption of $H_{2}O$ on oxygen vacancies, reducing the hole scavenging ability. The UV light intensity only affects the response time during the coloring stage, which decreases as the UV light intensity increases. Further, the practical applications of DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion deserve to be investigated. Considering the high transparency and large optical modulation amplitude, it can be applied to a photochromic window, which is composed of two quartz glasses and nanodispersion sealed in the middle. The photochromic window exhibits high transparency in the absence of UV irradiation and shows a dark blue color to serve as an optical shield after being fully irradiated with UV light. Moreover, the photochromic response of the nanodispersion to sunlight inspires the application potential of this photochromic window for solar heat and sunlight management. When exposed to sunlight, the photochromic window absorbs the UV light in sunlight and transforms to a tinted state, thereby reducing sunlight and solar heat entering the room. Importantly, the window is able to adjust its sunlight transmittance and heat absorption capacity in response to changes in sunlight intensity. Overall, this photochromic window, which is simple in structure, easy to use, and capable of being activated by low-power UV and sunlight, is of practical significance and opens up new avenues for the design of photochromic devices.

2.3. Density Functional Theory (DFT) Calculations

To further reveal the synergistic effect of epitaxial lattice strain and Rb doping on oxygen vacancy formation as well as the adsorption state of DEG on the particle surface, DFT calculations were performed to analyze the evolution of the oxygen vacancy formation energy and the DEG adsorption energy. According to the quasiharmonic approximation, the change in the Gibbs free energy of oxygen vacancy formation ($\Delta G$) has been shown that it can be described as a function of epitaxial strain ($\eta$) and temperature (T).
$\Delta G$ has been described as decreasing with increasing epitaxial strain at constant temperature, suggesting that strain is an effective means of increasing oxygen vacancy concentration. Here tensile strain from 0 to 3% was performed along the x, y, and z directions of the crystal, denoted as $TiO_{2}/TB(X)$, with X representing the strain level. As shown in Figure 4a, the oxygen vacancy formation energy gradually decreases with increasing lattice strain, implying that the lattice strain effectively reduces the energy barrier for the formation of oxygen vacancy. Furthermore, the doping of the low-valent metal ions generates an effective positive charge (hole state) at the anion lattice position, and oxygen vacancies are spontaneously formed by a charge compensation mechanism, which releases electrons to fill the formed holes, thus maintaining the charge neutrality of the material. The first main group elements with the lowest positive valence state (+1) are the optimal choice to significantly reduce the oxygen vacancy formation energy through the charge compensation mechanism. Among the common first main group elements (Li, Na, K, and Rb), Rb has a larger ionic radius, which may cause lattice distortions thereby altering the coordination environment to decrease the migration barrier for oxygen atom transfer and surface exchange. It has also been reported that Rb doping exhibits the most significant reduction in oxygen vacancy formation energy compared to Li, Na, and K. Correspondingly, Rb doping based on a 3% lattice strain further reduces the oxygen vacancy formation energy to a negative value, ensuring the spontaneous formation of oxygen vacancies. Therefore, lattice strain and Rb doping synergistically and significantly reduce $\Delta G$, which leads to an exponential increase in oxygen vacancy concentration. The increased oxygen vacancies facilitate the dissociative adsorption of DEG serving as SED to scavenge holes.

Since the adsorption state of DEG on the particle surface is crucial for the hole scavenging rate, the adsorption energies of two physisorbed configurations and one dissociatively adsorbed configuration of DEG on $TiO_{2}$ and $Rb-TiO_{2}/TB(3\%)$ were calculated. For $TiO_{2}$, the dissociative adsorption energy of DEG is more positive than the physical adsorption energy, indicating that the intact DEG physical adsorption configuration is more stable. Notably, the dissociative adsorption energy of DEG on $Rb-TiO_{2}/TB(3\%)$ at oxygen vacancy is more negative than the physical adsorption energy, indicating that DEG prefers to be dissociatively adsorbed at oxygen vacancy in $Rb-TiO_{2}/TB(3\%)$. In addition, compared to $TiO_{2}$, the physical adsorption and dissociative adsorption energies of DEG on $Rb-TiO_{2}/TB(3\%)$ exhibit a significant decrease, suggesting that both adsorptions are promoted on $Rb-TiO_{2}/TB(3\%)$. This facilitates the rapid scavenging of holes and stabilizes the coloring state by blocking $O_{2}$ through the physisorption layer of DEG. Figure 4c shows the density of states of $Rb-TiO_{2}/TB(3\%)$. The O 2p orbitals contribute the most to the top of the valence band (VB), and Ti 3d orbitals contribute the most to the bottom of the conduction band (CB). Possibly due to the presence of only one valence electron and small doping amount, the orbitals of Rb contribute little to CB and VB, without the introduction of intermediate energy levels in the bandgap. After physical or chemical adsorption, the density of states of $Rb-TiO_{2}/TB(3\%)$ shows no noticeable change, which indicates that the DEG adsorbed on the surface has no detrimental effect on the electronic structure of the crystal. The density of states of DEG before and after adsorption is displayed in Figure 4d. The bonding orbital energies of DEG in two adsorption states are both shifted in the negative direction, indicating the strong interaction between DEG and the surface of $Rb-TiO_{2}/TB(3\%)$. It is noteworthy that the two adsorption states correspond to different reductions in bonding orbital energy, suggesting that the dissociatively adsorbed surface can better stabilize the DEG, which is consistent with the results of the reduction in adsorption energy. Moreover, compared to physically adsorbed DEG, the O 2p orbital on the left side of the Fermi level of dissociatively adsorbed DEG is shifted toward higher energies, which is mainly contributed by the dissociative hydroxyl oxygens.

Additionally, to verify that it is the chemisorbed DEG that scavenges holes rather than the hydroxyl radicals formed by oxygenation of adsorbed water or solvent, MB was used as the probe molecule to study the mechanism. It is well known that MB can be degraded by oxidative species (such as holes, hydroxyl radicals, etc.) during the photocatalytic process, leading to irreversible discoloration. However, it is important to note that since the reduction potential of MB is lower than that of the photogenerated electrons of $TiO_{2}$, MB can also be reduced by these electrons to form the colorless leuco-methylene blue (LMB). The colorless LMB can subsequently be oxidized back to the colored MB by $O_{2}$, enabling reversible coloring. Therefore, the color change trend of the MB solution with the addition of $Rb-TiO_{2}/TB-CS$ after UV irradiation can provide insights into the behavior of holes in the photocatalytic process. As shown in Figure S28, the MB solution with $Rb-TiO_{2}/TB-CS$ completely fades after 120 s under UV irradiation, followed by gradual color recovery in the dark within 24 h. This indicates that MB is reduced to colorless LMB by photogenerated electrons and oxidized back to MB by $O_{2}$ in the air, demonstrating effective hole scavenging. However, MB solution containing commercial P25 exhibits minimal color change after 120 s of UV irradiation and completely fades after 70 min of UV irradiation, failing to recover its color in the dark. It can be attributed to the irreversible degradation by oxidative species generated via holes in MB solution containing commercial P25. Moreover, the DEG's role as a sacrificial electron donor for scavenging holes is further confirmed by fluorescence spectroscopy analysis. Furthermore, the gas chromatography (GC) analysis is applied to demonstrate the existence of oxidative dissociation products of DEG. As the data and experiment steps are presented in Figure S30, the oxidative dissociation products from DEG are successfully detected, and the percentage of oxidative dissociation products of polyols from solvent environments increases with increasing color-switching cycles. This demonstrates the role of DEG as the sacrificial electron donor to scavenge holes and the substitution of new ligands from the environment.

2.4. Photochromic Composite Materials Constructed with Rb-TiO2/TB-CS

The above advanced color-switching system was used as the responsive material for transparent photochromic display applications. We designed a polyacrylate-based hybrid material with DEG chemisorbed $Rb-TiO_{2}/TB-CS$ as the functional component. Poly(ethylene glycol) diacrylate (PEGDA) and methyl methacrylate (MMA) as monomers and pentaerythritol triacrylate (PETA) as a 3D crosslinker provide the polymer matrix with good strength and flexibility. The DPSi on the $Rb-TiO_{2}/TB-CS$ surface ensures the monodispersity of the nanoparticles, and APSi which possesses the acrylate structure acts as the site for the hybridization cross-linking reaction, facilitating the construction of a homogeneous and transparent $Rb-TiO_{2}/TB-CS$/acrylate photochromic hybrid film by UV curing. The $Rb-TiO_{2}/TB-CS$/acrylate hybrid film can be bent extensively and recovered, demonstrating excellent toughness and flexibility. The scanning electron microscopy (SEM) image and elemental maps of this hybrid film indicate a flat surface and uniform elemental distribution of the hybrid film. It can be seen from Figure 5b that the $Rb-TiO_{2}/TB-CS$/acrylate hybrid film shows excellent transparency in the colorless state and exhibits high contrast after UV irradiation. Transparent and colored states can be easily switched by UV irradiation and heat oxidation. In addition, customized contents can be clearly displayed on the hybrid film by UV irradiation using a photomask, which is easily prepared by inkjet printing on a transparent plastic sheet. As shown in Figure 5c, the exposed areas of the photomask turn dark blue after light printing, while the unexposed areas remain transparent, making it easy to light-print complex shapes and text with high resolution. Photo-printed content shows good stability and remains readable after 14 h at room temperature.

The photochromic response rate of hybrid films with different $Rb-TiO_{2}/TB-CS$ contents is further investigated. The thickness of the photochromic hybrid films is measured to be 0.8 mm. As seen in Figure 5d, the hybrid films with low $Rb-TiO_{2}/TB-CS$ content (5 wt.%, 10 wt.%) only exhibit slight coloration after 70 s of UV irradiation. With the increase of $Rb-TiO_{2}/TB-CS$ content, the coloration process is significantly accelerated. For the hybrid film with 40 wt.% $Rb-TiO_{2}/TB-CS$, the deep dark blue coloration can be accomplished within 30 s of UV irradiation. Additionally, the optical transmittance of the hybrid film in the colorless state is also an important performance index for its application. The polyacrylate film without $Rb-TiO_{2}/TB-CS$ exhibits a visible light transmittance greater than 90%, indicating excellent visible transparency. As the $Rb-TiO_{2}/TB-CS$ content increases, the visible transmittance of the hybrid films gradually decreases, while the UV-shielding ability increases. The decrease in visible transmittance is attributed to the combination of the lone pair electrons of the acrylate with the Lewis acid sites on the $TiO_{2}$ surface to form a dipole layer toward the inner $TiO_{2}$, which significantly enhances the exciton binding energy, leading to a red-shifting of the absorption band edges. The hybrid film with 20 wt.% $Rb-TiO_{2}/TB-CS$ still shows the transmittance of more than 85% at 650 nm and achieves a deep dark blue coloration after 70 s of UV irradiation, so it is chosen for further studies.

The color-switching performance and reversible stability of this hybrid film are also further investigated. As seen in Figure 5f, the transmittance of hybrid film with 20 wt.% $Rb-TiO_{2}/TB-CS$ gradually decreases with the increasing time of UV irradiation and reaches the minimum in 70 s, exhibiting an optical modulation amplitude of 82.74% at 650 nm, which demonstrates the rapid response and high contrast of this photochromic system. The photochromism performance of the hybrid film under sunlight is also investigated and displayed in Figure S34. The transmittance of hybrid film gradually approaches the minimum after 150 min of sunlight irradiation and the optical modulation amplitude is reduced to 60.7% at 650 nm. Nevertheless, the complex patterns and texts can still be photo-printed on hybrid film through a photomask under sunlight exposure. The deep dark blue hybrid film left in the air at room temperature takes 24 h to fully recover the transparent state. To accelerate the decoloration process, the hybrid film can be heated in air at 70°C, which reduces the recovery process to 70 min. The color-switching reversibility was also evaluated by studying the transmittance of hybrid film for coloration and decoloration in 20 repetitive cycles. The transmittance of the hybrid films shows no noticeable change after successive coloration-decoloration cycles and still exhibits an optical modulation amplitude exceeding 75% after 20 cycles, indicating the stable reversibility of the hybrid films dominated by $Rb-TiO_{2}/TB-CS$. Therefore, $Rb-TiO_{2}/TB-CS$/acrylate photochromic hybrid film exhibiting large optical modulation amplitude, rapid response, and stable reversibility has the potential to serve as an adaptable base material. For instance, it can be used to construct indoor transparent display devices. The transparent display glass exhibits good transparency to clearly present the scene behind the glass. The photo-printed contents can be clearly displayed with high contrast on the transparent base. In addition, photo-printing can be performed directly with a programmable UV laser without the use of a photomask. The utilization of $Rb-TiO_{2}/TB-CS$/acrylate hybrid film to construct the transparent display device is simple and feasible, representing a low-cost and advanced solution for transparent displays.

Moreover, $Rb-TiO_{2}/TB-CS$ also exhibits surprising application potential in aqueous substrates, showing good transparency and photochromic properties. As shown in Figure 6a, surface-grafted long-chain siloxane (DPSi) can adjust the surface properties to accommodate organic solvents and acrylate systems. However, in the aqueous solution, the modifiers may rotate and adhere to the surface without providing steric hindrance. Correspondingly, by adding ammonia to adjust the DEG-added $Rb-TiO_{2}/TB-CS$ aqueous solution to a weak base (pH 10), the zeta potential is measured to be -42.7 mV to prove the wide electric double layer of particles, suggesting that the particles can be monodispersed by mutual repulsion through electrostatic interactions. As shown in Figure S37, after 90 days of storage the aqueous nanodispersion (10 wt.%) still exhibits no precipitation and maintains excellent transparency. Considering the transparency maintained by electrostatic interactions in aqueous-based conditions, the hydrogel containing $Rb-TiO_{2}/TB-CS$ is suitable for further applications. PVA serves as the hydrogel matrix with water and ammonia to ensure the monodispersion of particles by electrostatic repulsion. The DEG chemisorbed on the particle surface not only acts as the SED to scavenge holes but also enhances the mechanical properties of the hydrogel through hydrogen bonds with the PVA matrix. Notably, the transparent $Rb-TiO_{2}/TB-CS$/PVA hydrogel can be significantly twisted and stretched (250%) in different color states, demonstrating good mechanical properties. Furthermore, the hydrogel can be easily adhered to the material surface, showing flexibility and convenience in application, which reveals its potential in applications such as oxygen indicators and wearable devices. Additionally, the construction of photochromic rewritable paper is another attractive application well-suited for $Rb-TiO_{2}/TB-CS$. By pouring and evaporating a mixed aqueous solution of $Rb-TiO_{2}/TB-CS$, DEG, and HEC on cardboard, $Rb-TiO_{2}/TB-CS$/HEC composite film was obtained for photochromic reversible writing. It can be seen clearly from Figure 6f that the high-resolution text in 10-point font size can be easily photo-printed through a photomask, which exhibits excellent readability. Complex and delicate patterns can also be printed (UV light) and erased (heat) reversibly, and photo-printed content can remain visible for up to 6 h in room condition. Therefore, $Rb-TiO_{2}/TB-CS$/HEC composite film can be used as reversible printing paper for short-term reading, such as temporary labels and confidential documents in conferences.

3. Conclusion

In conclusion, a highly efficient and stable $Rb-TiO_{2}/TB-CS$ structure is designed for constructing reversible photochromic systems. The oxygen vacancies engineering drastically enhances the photochromic performance of $TiO_{2}$. Structural analyses and DFT calculations indicate that Rb doping and tensile strain synergistically promote the generation of oxygen vacancies and facilitate the DEG adsorption on the $TiO_{2}$ surface. Chemisorbed DEG acts as the efficient SED to rapidly scavenge holes, and physisorbed DEG may block $O_{2}$ to stabilize the coloring state. The engineered DEG-added $Rb-TiO_{2}/TB-CS$ nanodispersion shows a significant optical modulation amplitude exceeding 90% at 650 nm, rapid response within 60 s, and stable reversibility, which can be used to construct photochromic windows. Additionally, the $Rb-TiO_{2}/TB-CS$ nanoparticles are modified using composite siloxanes to be monodispersed with an average size of 11.7 nm and improve the organic-inorganic compatibility, which enables the high transparency of photochromic composite materials. The transparent $Rb-TiO_{2}/TB-CS$/acrylate photochromic hybrid film possesses good flexibility and shows an optical contrast of 82.74% at 650 nm before and after UV irradiation, which enables photo-printing of complex contents, showing great potential for transparent display applications. The $Rb-TiO_{2}/TB-CS$/PVA photochromic hydrogel shows great transparency, stretchability, twistability, and adhesiveness, indicating the application potential in wearable devices. In addition, the $Rb-TiO_{2}/TB-CS$/HEC rewritable films can be used as reversible printing paper for short-term reading. Therefore, the $Rb-TiO_{2}/TB-CS$ structure, which is compatible, low-cost, stable, and nontoxic, is an excellent versatile responsive material for photochromic systems and opens up new opportunities in various color-switching applications.

4. Experimental Section

Materials: Benzyl alcohol (BnOH, ≥99%), titanium butoxide (TBOT, ≥99%), rubidium nitrate (RbNO3, ≥99.9%), 3-(acryloyloxy) propyltrimethoxysilane (APSi, ≥99%), 3,3-dimethoxy-2,7,10,13,16-pentaoxa-3-silaheptadecane (DPSi, ≥97%), methylene blue (MB, AR), propylene glycol monomethyl ether acetate (PGMEA, ≥99.5%), diethylene glycol (DEG, ≥99%), poly(ethylene glycol) diacrylate (PEGDA, Mw ≈ 575), polyvinyl alcohol (PVA, Mw ≈ 195000) and hydroxyethyl cellulose (HEC, 250–450 mPa·s) were provided by Shanghai Macklin Biochemical Co., Ltd. Methyl methacrylate (MMA, ≥99%), pentaerythritol triacrylate (PETA, ≥96%), and diphenyl (2,4,6-trimethylbenzoyl) phosphine oxide (TPO, ≥97%) were obtained from Shanghai Aladdin Biochemical Technology Co., Ltd. Acetic acid (HAc, ≥99.5%), ethanol (EtOH, ≥99.7%), n-heptane (C7H16, ≥98.5%), ammonium hydroxide (NH3·H2O, 28%) and acetone (DMK, AR) were obtained from Sinopharm Chemical Reagent Co., Ltd.

Synthesis of Rb-TiO2/TB Nanoparticles: Typically, 0.2 mL of HAc, 0.8 mL of H2O, 0.18 g of RbNO3, and 6 mL of TBOT were sequentially dissolved in 25 mL of BnOH under stirring. The above precursor solution was transferred to a Teflon-lined autoclave and heated at 200 °C for 2 h. Then the 1.2 mL of TBOT and 30 µL of H2O were successively added to the above reaction system under stirring, and the mixture solution was sealed and heated at 300 °C for 1 h. The products were separated by centrifugation and washed with PGMEA 3 times. The precipitate was heated at 80 °C for 12 h to obtain the dry powder noted as $Rb-TiO_{2}/TB$. Additionally, the pure $TiO_{2}$ was prepared without the secondary addition of TBOT and H2O, and the $TiO_{2}/TB$ was prepared without the addition of RbNO3.

Preparation of Rb-TiO2/TB-CS Nanoparticles and Nanodispersions: The 1.5 g of undried $Rb-TiO_{2}/TB$ precipitate and 0.25 g of DPSi were added to 10 mL of PGMEA at 130 °C with stirring for 50 min, and then 0.05 g of APSi was added to the mixture with stirring for another 10 min to form a transparent dispersion. The dispersion was precipitated by adding n-heptane as anti-solvent and after centrifugation the precipitate was re-dispersed in acetone. After repeating the backwashing operation 3 times, the precipitate was placed under a vacuum for 2 h to obtain the dry powder noted as $Rb-TiO_{2}/TB-CS$. The 1 g of $Rb-TiO_{2}/TB-CS$ powder was added to 8 mL of PGMEA and 2 mL DEG under stirring to form the transparent $Rb-TiO_{2}/TB-CS$ photochromic nanodispersion (volume ratio, PGMEA:DEG = 4:1). The 1 g of $Rb-TiO_{2}/TB-CS$ powder, and 0.5 mL of NH3·H2O were added to 10 mL of H2O under stirring to form the transparent $Rb-TiO_{2}/TB-CS$ aqueous nanodispersion. Additionally, $TiO_{2}-CS$ and $TiO_{2}/TB-CS$ nanoparticles and nanodispersions were also prepared in the same way.

Preparation of Rb-TiO2/TB-CS/Acrylate Photochromic Hybrid Films: The 1 g of $Rb-TiO_{2}/TB-CS$ powder, 1.5 mL of MMA, 2.5 mL of PEGDA, 0.2 mL of DEG, 0.4 g of PETA, and 35 mg of TPO were added to 10 mL of acetone under stirring to form the homogeneous precursor solution. After evaporating the solvent (acetone) at 80 °C, the transparent $Rb-TiO_{2}/TB-CS$/acrylate photochromic hybrid film was obtained by UV curing the mixture in a glass mold.

Preparation of Rb-TiO2/TB-CS/PVA Photochromic Hydrogels: The aqueous glue was prepared by dissolving 3 g PVA in 30 mL H2O at 100 °C. The 10 mL of aqueous glue, 5 mL of $Rb-TiO_{2}/TB-CS$ aqueous nanodispersion, and 0.5 mL of DEG were mixed to form a homogeneous glue, and then the glue was cast onto a glass mold and heated at 60 °C to fabricate a transparent hydrogel.

Preparation of Rb-TiO2/TB-CS/HEC Rewritable Films: The HEC stock solution was prepared by dissolving 2 g HEC in 30 mL H2O at 80 °C for 2 h. The 10 mL of $Rb-TiO_{2}/TB-CS$ aqueous nanodispersion, 2 mL of DEG, and 15 mL of HEC stock solution were mixed and stirred for 1 h before film deposition. The mixture was cast onto a cardboard mold and heated at 70 °C for 12 h to form a composite photochromic film.

Cyclic Tests for Photochromism and Discoloration: The LED device (18 W, λ = 365 nm) was used as the UV light source with a light intensity of 70 mW cm$^{-2}$. For the testing of $Rb-TiO_{2}/TB-CS$ photochromic nanodispersion (volume ratio, PGMEA: DEG = 4:1), the visible light transmittance of the solution was measured after 60 s of UV irradiation, then air was injected into the solution for complete discoloration and the transmittance was measured again. The above operation is counted as one cycle. For the testing of $Rb-TiO_{2}/TB-CS$/acrylate hybrid photochromic films, the UV irradiation time was 70 s and the discoloration condition was dark treatment for 24 h.        """
    )

    feedback = ""
    previous_feedback = None
    previous_final_question = None
    log_path = Path(QUESTION_LOG_PATH)
    for round_idx in range(1, MAX_ROUNDS + 1):
        print(f"\n=== 第 {round_idx} 轮生成 ===")
        stage_one, stage_two, stage_three, stage_final = generate_questions(
            context,
            image_path,
            feedback,
            previous_final_question,
        )
        save_round_questions(log_path, round_idx, stage_one, stage_two, stage_three, stage_final)
        previous_final_question = stage_final.question

        try:
            solver_raw, solver_letter = try_solve_question(context, stage_final.question, image_path)
            standard_letter = parse_option_letter(stage_final.answer)
        except Exception as exc:  # noqa: BLE001
            print(f"求解阶段失败，终止: {exc}")
            break

        if solver_letter != standard_letter:
            print("求解模型未能正确作答，循环结束。")
            break

        analysis_prompt = build_analysis_prompt(stage_final.question, stage_final.answer, solver_raw)
        feedback = call_text_model(analysis_prompt, MODEL_ANALYSIS)
        normalized_feedback = feedback.strip()
        print("难度提升指引:", feedback)
        if previous_feedback is not None and normalized_feedback == previous_feedback:
            print("难度提升指引已收敛，停止。")
            break
        previous_feedback = normalized_feedback
    else:
        print("已达到最大轮次，停止。")


if __name__ == "__main__":
    main()
