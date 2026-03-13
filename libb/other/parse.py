import json
import re
def parse_json(text: str, tag: str):
    # Extract the block from given section
    pattern = rf"<{re.escape(tag)}>\s*(\{{.*?\}})\s*</{re.escape(tag)}>"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No {tag} block found.")
    json_str = match.group(1)
    # Strip markdown code fences if the LLM wrapped the JSON in ```json ... ```
    json_str = re.sub(r"^```(?:json)?\s*", "", json_str.strip())
    json_str = re.sub(r"\s*```$", "", json_str)
    # Unescape Python-style double braces {{ }} that some models copy from the prompt template
    json_str = json_str.replace("{{", "{").replace("}}", "}")
    # Remove trailing commas before } or ] (common LLM mistake)
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    return json.loads(json_str)
