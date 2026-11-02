"""Optional Claude step. Only runs when ANTHROPIC_API_KEY is set; any failure falls back to the rules text."""
import json
import os


def claude_summary(facts):
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        prompt = ("You are a RevOps lead summarising one inbound lead batch for the sales and marketing managers. "
                  "Use ONLY the facts in this JSON. Do not invent numbers, names or causes. Write 4 to 6 plain sentences, "
                  "no emojis, no bullet points: what came in, what is ready to import, what needs a human and why, "
                  "and the one fix that would remove the most review work next time.\n\n" + json.dumps(facts, default=str))
        msg = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"), max_tokens=600,
                                     messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip()
    except Exception as e:  # the optional step must never break the run
        print(f"  Claude step skipped ({type(e).__name__}); using the rules summary.")
        return None
