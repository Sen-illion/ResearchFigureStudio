from __future__ import annotations

import json
import re
from typing import Any

from ..vlm_client import call_vlm_json, resolve_vlm_model, vlm_credentials_available
from .analyzer import evidence_excerpt


DEFAULT_PREFERENCES = {
    "summary": "Default paper-to-image preferences.",
    "figure_type": "method framework figure",
    "aspect_ratio": "16:9",
    "language": "English",
    "style_description": "clean academic illustration, restrained 2.5D, dense but readable",
    "preferred_flow": "left_to_right",
    "visual_density": "high",
    "preferred_palette": ["blue", "teal", "warm orange accent"],
    "avoid": ["cyberpunk", "commercial poster", "generic dashboard cards", "unrelated robots", "fake charts"],
    "must_show": [],
    "must_not_show": [],
}


def merge_preferences(raw: dict | None, aspect_ratio: str | None = None, language: str | None = None) -> dict:
    merged = dict(DEFAULT_PREFERENCES)
    if isinstance(raw, dict):
        merged.update(raw)
    if aspect_ratio:
        merged["aspect_ratio"] = aspect_ratio
    if language:
        merged["language"] = language
    merged["summary"] = "User and default preferences compiled for image generation."
    return merged


def _planner_prompt(parsed: dict, preferences: dict, paper_review: dict | None = None) -> str:
    return f"""
# Summary

You are a paper-to-scientific-figure planner. Return JSON only.

Build a scientifically faithful plan for generating ONE complete raster framework figure from the supplied paper evidence. Do not create PPTX instructions. Do not invent stock modules such as encoder, retriever, memory, agent, reinforcement learning, knowledge base, or decoder unless supported by evidence.

Every important factual item must include one or more evidence_ids copied exactly from the supplied evidence labels. Mark uncertain fields as unknown. Use the paper's exact terminology.

Return this schema:
{{
  "summary": "Paper-to-image planning result.",
  "paper_summary": {{
    "summary": "Structured paper summary.",
    "title": "...",
    "paper_type": "method|system|dataset|benchmark|analysis|survey|application|unknown",
    "research_problem": {{"text": "...", "evidence_ids": ["E0001"]}},
    "central_claim": {{"text": "...", "evidence_ids": ["E0001"]}},
    "inputs": [{{"name": "...", "evidence_ids": ["E0001"]}}],
    "outputs": [{{"name": "...", "evidence_ids": ["E0001"]}}],
    "core_modules": [{{"id": "stable_id", "name": "exact paper term", "role": "...", "evidence_ids": ["E0001"]}}],
    "innovations": [{{"text": "...", "evidence_ids": ["E0001"]}}],
    "training_flow": [{{"step": "...", "evidence_ids": ["E0001"]}}],
    "inference_flow": [{{"step": "...", "evidence_ids": ["E0001"]}}],
    "terminology": {{"Exact Term": "required visible label"}},
    "unknowns": []
  }},
  "figure_specification": {{
    "summary": "Scientific contract for the figure.",
    "figure_goal": "...",
    "storyline": [],
    "must_show": [{{"text": "...", "evidence_ids": ["E0001"]}}],
    "modules": [{{"id": "...", "name": "...", "role": "...", "evidence_ids": ["E0001"]}}],
    "relations": [{{"source": "module_id", "target": "module_id", "type": "data_flow|control_flow|training_only|inference_only|comparison|feedback", "label": "", "evidence_ids": ["E0001"]}}],
    "inputs": [],
    "outputs": [],
    "innovations": [],
    "visual_priorities": [],
    "terminology": {{}},
    "forbidden_inventions": []
  }},
  "design_plan": {{
    "summary": "Information narrative for one complete image.",
    "reading_order": [],
    "groups": [],
    "innovation_emphasis": [],
    "preserve": [],
    "remove": []
  }},
  "layout_intent": {{
    "summary": "Layout intent for the image model.",
    "pattern": "left_to_right|two_stage|hub_and_spoke|loop|stacked|before_after",
    "canvas_ratio": "16:9",
    "regions": [{{"id": "...", "position": "left|center|right|top|bottom", "relative_size": "small|medium|large", "contains": []}}],
    "flow_description": "...",
    "whitespace": "..."
  }},
  "visual_metaphors": {{
    "summary": "Concrete visual objects for paper concepts.",
    "items": [{{"module_id": "...", "metaphor": "concrete visible objects", "must_show": [], "avoid_showing": []}}]
  }},
  "style_plan": {{
    "summary": "Image style contract.",
    "medium": "...",
    "palette": [],
    "viewpoint": "...",
    "line_and_shadow": "...",
    "visual_density": "...",
    "background": "...",
    "text_policy": "short exact labels only; no paragraphs, fake equations, fake axes, or invented numbers",
    "positive_reference_rules": [],
    "negative_reference_rules": []
  }}
}}

User preferences:
{json.dumps(preferences, ensure_ascii=False, indent=2)}

Universal structured paper review:
{json.dumps(paper_review or {}, ensure_ascii=False, indent=2)}

Paper evidence:
{evidence_excerpt(parsed)}
""".strip()


def _first_sentence(text: str) -> str:
    sentences = [item.strip() for item in re.split(r"(?<=[.!?。！？])\s+", text) if len(item.strip()) > 20]
    return sentences[0][:500] if sentences else text[:500].strip()


def _heuristic_plan(parsed: dict, preferences: dict, paper_review: dict | None = None) -> dict:
    if paper_review and paper_review.get("modules"):
        review_modules = paper_review.get("modules", [])[:10]
        modules = [{"id": str(item.get("id")), "name": str(item.get("visible_label") or item.get("statement") or item.get("id")), "role": str(item.get("visual_role") or "module"), "evidence_ids": list(item.get("evidence_ids", []))} for item in review_modules]
        relations = [{"source": str(item.get("source_id") or item.get("source") or ""), "target": str(item.get("target_id") or item.get("target") or ""), "type": str(item.get("relation_type") or item.get("type") or "data_flow"), "label": str(item.get("statement") or "")[:48], "evidence_ids": list(item.get("evidence_ids", []))} for item in paper_review.get("relations", []) if (item.get("source_id") or item.get("source")) and (item.get("target_id") or item.get("target"))]
        terminology = {str(item.get("statement")): str(item.get("visible_label") or item.get("statement")) for item in paper_review.get("terminology", []) if str(item.get("statement") or "").strip()}
        title = str(paper_review.get("paper_identity", {}).get("title") or parsed.get("source_name"))
        research_questions = paper_review.get("research_questions", [])
        claims = paper_review.get("central_claims", [])
        figure_goal = str((claims or research_questions or [{"statement": "Explain the paper method faithfully."}])[0].get("statement"))
        innovations = paper_review.get("innovations", [])
        forbidden = [str(item.get("statement")) for item in paper_review.get("forbidden_inventions", [])]
        inputs = paper_review.get("inputs", [])
        outputs = paper_review.get("outputs", [])
        return {
            "summary": "Paper-review-grounded fallback planning result.",
            "paper_summary": {"summary": "Structured paper summary derived from paper_review.json.", "title": title, "paper_type": paper_review.get("paper_identity", {}).get("paper_type", "unknown"), "research_problem": (research_questions or [{}])[0], "central_claim": (claims or [{}])[0], "inputs": inputs, "outputs": outputs, "core_modules": modules, "innovations": innovations, "training_flow": paper_review.get("workflows", {}).get("training", []), "inference_flow": paper_review.get("workflows", {}).get("inference", []), "terminology": terminology, "unknowns": paper_review.get("unknowns", [])},
            "figure_specification": {"summary": "Scientific contract derived from universal paper review.", "figure_goal": figure_goal, "storyline": [item["id"] for item in modules], "must_show": [{"text": item["name"], "evidence_ids": item["evidence_ids"]} for item in modules], "modules": modules, "relations": relations, "inputs": inputs, "outputs": outputs, "innovations": innovations, "visual_priorities": [item["name"] for item in modules if item["role"] in {"module", "innovation"}], "terminology": terminology, "forbidden_inventions": forbidden},
            "design_plan": {"summary": "Paper-review-grounded information narrative.", "reading_order": [item["id"] for item in modules], "groups": [], "innovation_emphasis": [item.get("statement") for item in innovations], "preserve": [item["name"] for item in modules], "remove": forbidden},
            "layout_intent": {"summary": "Layout intent awaiting template selection.", "pattern": "left_to_right", "canvas_ratio": preferences.get("aspect_ratio", "auto"), "regions": [], "flow_description": "Follow the selected reference template while preserving paper relations.", "whitespace": "reference-matched"},
            "visual_metaphors": {"summary": "Concrete visual metaphors grounded in review roles.", "items": [{"module_id": item["id"], "metaphor": f"dense academic visual scene for {item['name']}", "must_show": [item["name"]], "avoid_showing": forbidden} for item in modules]},
            "style_plan": {"summary": "Style plan will inherit the selected reference template.", "medium": preferences.get("style_description"), "palette": preferences.get("preferred_palette", []), "viewpoint": "reference-matched academic diagram", "line_and_shadow": "reference-derived", "visual_density": preferences.get("visual_density", "high"), "background": "clean light background", "text_policy": "Image2 renders only exact short labels from the whitelist.", "positive_reference_rules": [], "negative_reference_rules": preferences.get("avoid", [])},
        }
    evidence = parsed["evidence"]
    headings = parsed.get("headings", [])
    first = evidence[0]
    title = next((line.strip() for line in first["text"].splitlines() if 10 <= len(line.strip()) <= 180), parsed["source_name"])
    generic = {"abstract", "introduction", "related work", "method", "methods", "experiments", "results", "conclusion", "references"}
    names = [item for item in headings if item.lower() not in generic][:6]
    if len(names) < 3:
        names = ["Research Input", "Core Method", "Research Output"]
    modules = []
    for index, name in enumerate(names):
        evidence_id = evidence[min(index, len(evidence) - 1)]["id"]
        modules.append({"id": f"module_{index + 1:02d}", "name": name, "role": "paper-derived stage requiring VLM verification", "evidence_ids": [evidence_id]})
    relations = [
        {"source": modules[index]["id"], "target": modules[index + 1]["id"], "type": "data_flow", "label": "", "evidence_ids": list(dict.fromkeys(modules[index]["evidence_ids"] + modules[index + 1]["evidence_ids"]))}
        for index in range(len(modules) - 1)
    ]
    central = _first_sentence(first["text"])
    return {
        "summary": "Heuristic paper-to-image planning result; scientific details require review.",
        "paper_summary": {
            "summary": "Heuristic structured paper summary.",
            "title": title,
            "paper_type": "unknown",
            "research_problem": {"text": central, "evidence_ids": [first["id"]]},
            "central_claim": {"text": "unknown", "evidence_ids": []},
            "inputs": [],
            "outputs": [],
            "core_modules": modules,
            "innovations": [],
            "training_flow": [],
            "inference_flow": [],
            "terminology": {item["name"]: item["name"] for item in modules},
            "unknowns": ["central claim", "training flow", "inference flow", "innovations"],
        },
        "figure_specification": {
            "summary": "Heuristic scientific contract for the figure.",
            "figure_goal": "Summarize the paper's main flow without inventing unsupported details.",
            "storyline": [item["name"] for item in modules],
            "must_show": [{"text": item["name"], "evidence_ids": item["evidence_ids"]} for item in modules],
            "modules": modules,
            "relations": relations,
            "inputs": [],
            "outputs": [],
            "innovations": [],
            "visual_priorities": [item["name"] for item in modules],
            "terminology": {item["name"]: item["name"] for item in modules},
            "forbidden_inventions": ["unsupported external knowledge base", "unsupported reinforcement learning", "unsupported agent or memory module"],
        },
        "design_plan": {
            "summary": "Heuristic left-to-right information narrative.",
            "reading_order": [item["id"] for item in modules],
            "groups": [],
            "innovation_emphasis": [],
            "preserve": [item["name"] for item in modules],
            "remove": ["unsupported generic AI decorations"],
        },
        "layout_intent": {
            "summary": "Heuristic layout intent.",
            "pattern": preferences.get("preferred_flow") or "left_to_right",
            "canvas_ratio": preferences.get("aspect_ratio", "16:9"),
            "regions": [{"id": item["id"], "position": "left" if index == 0 else "right" if index == len(modules) - 1 else "center", "relative_size": "medium", "contains": [item["id"]]} for index, item in enumerate(modules)],
            "flow_description": "A clear left-to-right scientific pipeline.",
            "whitespace": "moderate",
        },
        "visual_metaphors": {
            "summary": "Concrete fallback visual metaphors.",
            "items": [{"module_id": item["id"], "metaphor": f"dense academic mini-scene representing {item['name']}", "must_show": ["paper-specific structure", "visible process cue"], "avoid_showing": ["generic robot", "fake chart"]} for item in modules],
        },
        "style_plan": {
            "summary": "Style plan compiled from user preferences.",
            "medium": preferences.get("style_description"),
            "palette": preferences.get("preferred_palette", []),
            "viewpoint": "front-facing academic diagram",
            "line_and_shadow": "crisp thin lines with restrained soft shadows",
            "visual_density": preferences.get("visual_density", "high"),
            "background": "clean light background",
            "text_policy": "short exact labels only; no paragraphs, fake equations, fake axes, or invented numbers",
            "positive_reference_rules": [],
            "negative_reference_rules": preferences.get("avoid", []),
        },
    }


def _ensure_summary(value: Any, fallback: str) -> dict:
    data = value if isinstance(value, dict) else {}
    data.setdefault("summary", fallback)
    return data


def normalize_plan(raw: dict, preferences: dict) -> dict:
    result = raw if isinstance(raw, dict) else {}
    result.setdefault("summary", "Paper-to-image planning result.")
    result["paper_summary"] = _ensure_summary(result.get("paper_summary"), "Structured paper summary.")
    result["figure_specification"] = _ensure_summary(result.get("figure_specification"), "Scientific contract for the figure.")
    result["design_plan"] = _ensure_summary(result.get("design_plan"), "Information narrative for the figure.")
    result["layout_intent"] = _ensure_summary(result.get("layout_intent"), "Layout intent for the image model.")
    result["visual_metaphors"] = _ensure_summary(result.get("visual_metaphors"), "Concrete visual metaphors.")
    result["style_plan"] = _ensure_summary(result.get("style_plan"), "Image style contract.")
    result["layout_intent"].setdefault("canvas_ratio", preferences.get("aspect_ratio", "16:9"))
    return result


def plan_paper_image(parsed: dict, preferences: dict, mode: str = "vlm", model: str | None = None, reference_images: list[str] | None = None, paper_review: dict | None = None) -> tuple[dict, dict]:
    prompt = _planner_prompt(parsed, preferences, paper_review=paper_review)
    metadata = {"requested_mode": mode, "mode": mode, "model": None, "warning": None, "prompt": prompt}
    if mode == "vlm" and vlm_credentials_available():
        resolved = resolve_vlm_model("RFS_PAPER_TO_IMAGE_MODEL", "RFS_PAPER_PLANNER_MODEL", explicit_model=model)
        try:
            raw = call_vlm_json(prompt, reference_images or [], model=resolved, timeout=240, retries=1)
            metadata["model"] = resolved
            return normalize_plan(raw, preferences), metadata
        except Exception as exc:
            metadata.update({"mode": "heuristic_after_vlm_failure", "warning": str(exc), "model": resolved})
    elif mode == "vlm":
        metadata.update({"mode": "heuristic_without_credentials", "warning": "API_BASE and API_KEY/GEMINI_API_KEY are required for VLM planning"})
    return normalize_plan(_heuristic_plan(parsed, preferences, paper_review=paper_review), preferences), metadata


def compile_image_prompt(plan: dict, preferences: dict, candidate_variant: int = 1, selected_template: dict | None = None) -> str:
    spec = plan["figure_specification"]
    design = plan["design_plan"]
    layout = plan["layout_intent"]
    metaphors = plan["visual_metaphors"]
    style = plan["style_plan"]
    template = selected_template or {}
    labels = []
    terminology = spec.get("terminology", {})
    if isinstance(terminology, dict):
        labels.extend(str(value) for value in terminology.values())
    for module in spec.get("modules", []):
        if isinstance(module, dict):
            labels.append(str(module.get("name") or ""))
    labels = list(dict.fromkeys(label.strip() for label in labels if label.strip() and len(label.strip()) <= 48))[:24]
    return f"""
# Summary

Create one complete publication-quality scientific framework figure as a raster image.

Candidate variant: {candidate_variant}.
Scientific goal: {spec.get('figure_goal')}.
Target canvas ratio: {preferences.get('aspect_ratio', '16:9')}.
Text language: {preferences.get('language', 'English')}.

Scientific contract:
{json.dumps(spec, ensure_ascii=False, indent=2)}

Information narrative:
{json.dumps(design, ensure_ascii=False, indent=2)}

Layout intent:
{json.dumps(layout, ensure_ascii=False, indent=2)}

Concrete visual metaphors:
{json.dumps(metaphors, ensure_ascii=False, indent=2)}

Style contract:
{json.dumps(style, ensure_ascii=False, indent=2)}

Reference-derived content-free template contract:
{json.dumps({key: template.get(key) for key in ['template_id', 'panels', 'connectors', 'visual_density', 'style', 'selection']}, ensure_ascii=False, indent=2)}

Exact visible label whitelist (render these exactly and do not invent alternatives):
{json.dumps(labels, ensure_ascii=False)}

Forbidden copied reference terms:
{json.dumps(template.get('forbidden_copy_terms', []), ensure_ascii=False)}

Hard requirements:
- Preserve every paper-supported core module and relation.
- Use the exact short labels listed in terminology when labels are necessary.
- Make arrows unambiguous and follow the specified source-to-target direction.
- Emphasize the paper's actual innovation rather than generic AI decoration.
- Use a clean academic composition with dense but readable information hierarchy.
- Keep all major objects complete and inside the canvas; avoid large blank margins.
- Do not invent datasets, mechanisms, formulas, metrics, modules, or results.
- Do not render paragraphs, citations, fake equations, fake axes, fake charts, or invented numbers.
- Avoid commercial-poster styling, cyberpunk effects, unrelated robots, generic brains, and repeated dashboard cards.
- Treat the supplied blueprint as a hard macro-layout guide, but replace all reference content with this paper's content.
- Every visible scientific word must come from the exact label whitelist; do not paraphrase labels.
""".strip()


def validate_plan_grounding(plan: dict, parsed: dict) -> dict:
    valid_evidence = {item["id"] for item in parsed.get("evidence", [])}
    errors: list[str] = []
    warnings: list[str] = []
    spec = plan.get("figure_specification", {})
    def endpoint_id(item) -> str:
        if isinstance(item, dict):
            return str(item.get("id") or "").strip()
        return str(item or "").strip()

    modules = spec.get("modules") if isinstance(spec.get("modules"), list) else []
    if not modules:
        errors.append("figure_specification.modules is empty")
    module_ids: set[str] = set()
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            errors.append(f"module {index + 1} is not an object")
            continue
        module_id = str(module.get("id") or "").strip()
        if not module_id:
            errors.append(f"module {index + 1} has no id")
        elif module_id in module_ids:
            errors.append(f"duplicate module id: {module_id}")
        else:
            module_ids.add(module_id)
        evidence_ids = module.get("evidence_ids") if isinstance(module.get("evidence_ids"), list) else []
        if not evidence_ids:
            errors.append(f"module {module_id or index + 1} has no evidence_ids")
        invalid = [item for item in evidence_ids if item not in valid_evidence]
        if invalid:
            errors.append(f"module {module_id or index + 1} references unknown evidence ids: {invalid}")

    endpoint_ids = set(module_ids)
    for field in ("inputs", "outputs", "innovations"):
        items = spec.get(field) if isinstance(spec.get(field), list) else []
        endpoint_ids.update(value for value in (endpoint_id(item) for item in items) if value)

    relations = spec.get("relations") if isinstance(spec.get("relations"), list) else []
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append(f"relation {index + 1} is not an object")
            continue
        source = str(relation.get("source") or "").strip()
        target = str(relation.get("target") or "").strip()
        if source not in endpoint_ids or target not in endpoint_ids:
            errors.append(f"relation {index + 1} has unknown endpoint: {source} -> {target}")
        evidence_ids = relation.get("evidence_ids") if isinstance(relation.get("evidence_ids"), list) else []
        if not evidence_ids:
            warnings.append(f"relation {source} -> {target} has no evidence_ids")
        invalid = [item for item in evidence_ids if item not in valid_evidence]
        if invalid:
            errors.append(f"relation {source} -> {target} references unknown evidence ids: {invalid}")

    for field in ("must_show", "innovations"):
        items = spec.get(field) if isinstance(spec.get(field), list) else []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            evidence_ids = item.get("evidence_ids") if isinstance(item.get("evidence_ids"), list) else []
            invalid = [value for value in evidence_ids if value not in valid_evidence]
            if invalid:
                errors.append(f"{field}[{index}] references unknown evidence ids: {invalid}")

    return {
        "summary": "Scientific grounding and relation-contract validation.",
        "ok": not errors,
        "module_count": len(modules),
        "relation_count": len(relations),
        "evidence_count": len(valid_evidence),
        "errors": errors,
        "warnings": warnings,
    }
