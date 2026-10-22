"""Deploy only the browser/session proxy to the approved private test Space.

CPU orchestration belongs to the managed ConvFill worker pool. LOAD_BALANCER_URL
and LB_HF_TOKEN are explicit server-side values; existing Serper secrets stay put.
"""

import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi


def main():
    repo = "smolagents/convfill-speech-demo"
    root = Path(__file__).resolve().parents[1]
    url = os.environ["LOAD_BALANCER_URL"].strip()
    if not url.startswith("https://"):
        raise ValueError("The session service must use HTTPS")
    service_key = os.environ["LB_HF_TOKEN"]
    api = HfApi(token=os.environ["HF_TOKEN"])
    if not api.space_info(repo).private:
        raise ValueError("Refusing to deploy this private demo to a public Space")
    api.add_space_secret(repo, "LOAD_BALANCER_URL", url)
    api.add_space_secret(repo, "LB_HF_TOKEN", service_key)
    api.add_space_variable(
        repo,
        "STARTUP_GREETING",
        os.environ.get("STARTUP_GREETING", "Greet the user warmly in one short sentence, then invite them to talk."),
    )
    with tempfile.TemporaryDirectory(prefix="convfill-frontend-") as temporary:
        target = Path(temporary)
        shutil.copy2(root / "Dockerfile", target / "Dockerfile")
        shutil.copy2(root / "LICENSE", target / "LICENSE")
        shutil.copytree(
            root / "web_demo/hf_interface",
            target / "demo",
            ignore=shutil.ignore_patterns(
                "node_modules", "__pycache__", "*.pyc", ".env", "*.log", "server.py", "test_server.py"
            ),
        )
        for name in ["server.py", "auth.py", "limiter.py", "requirements.txt"]:
            shutil.copy2(root / "deploy/frontend" / name, target / "demo" / name)
        (target / "README.md").write_text(
            "---\ntitle: ConvFill Gemma Voice Demo\nemoji: 🎙️\ncolorFrom: blue\ncolorTo: green\nsdk: docker\napp_port: 7860\nhf_oauth: true\npinned: false\n---\n\nPrivate ConvFill browser UI backed by the managed smolagents pipeline pool.\n"
        )
        commit = api.upload_folder(
            repo_id=repo,
            repo_type="space",
            folder_path=target,
            commit_message="Use managed ConvFill pipelines through the session service",
        )
    print("Frontend Space revision:", commit.oid)


if __name__ == "__main__":
    main()
