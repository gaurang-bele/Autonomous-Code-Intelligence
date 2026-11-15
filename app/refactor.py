from app.config import get_settings

def generate_refactor(filename, code, lint_report, feedback=""):
    cfg = get_settings()
    if cfg.llm_provider.lower() == "mock" or not cfg.openai_api_key:
        # Offline mode is deliberately conservative; use an API key for semantic refactoring.
        cleaned = "\n".join(line.rstrip() for line in code.splitlines())
        return cleaned + ("\n" if code.endswith("\n") or cleaned else "")
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    llm = ChatOpenAI(model=cfg.llm_model, temperature=0, api_key=cfg.openai_api_key)
    messages = [
        SystemMessage(content="You are a senior Python engineer. Preserve behavior and public interfaces. Fix reported lint issues and incorporate reviewer feedback safely. Return only the complete replacement source code, no Markdown fences."),
        HumanMessage(content=f"File: {filename}\nLint report:\n{lint_report}\nReviewer feedback:\n{feedback or '(none)'}\nOriginal source:\n{code}")
    ]
    result = llm.invoke(messages).content
    if not isinstance(result, str):
        raise RuntimeError("LLM returned non-text content")
    result = result.strip()
    if result.startswith("```"):
        result = result.split("\n", 1)[-1]
        if result.endswith("```"):
            result = result[:-3]
    return result.lstrip("\n")
