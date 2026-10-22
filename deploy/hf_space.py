"""Publish this demo to the explicitly approved private smolagents Space.

HF_TOKEN is used only by the server and Hub API, never written into the source
bundle. Endpoints must belong to smolagents; check their control-plane metadata
before supplying URLs. No HuggingFaceM4 resources are read or modified.
"""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

from huggingface_hub import HfApi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='smolagents/convfill-speech-demo')
    args = parser.parse_args()
    if args.repo != 'smolagents/convfill-speech-demo':
        raise ValueError('This deployment is scoped to the approved smolagents Space')
    root = Path(__file__).resolve().parents[1]
    urls = {stage: os.environ['CONVFILL_' + stage + '_URL'] for stage in ['REASONER', 'TALKER', 'STT', 'TTS']}
    if any(not value.startswith('https://') for value in urls.values()):
        raise ValueError('Hosted inference URLs must use HTTPS')
    api = HfApi(token=os.environ['HF_TOKEN'])
    api.create_repo(args.repo, repo_type='space', space_sdk='docker', private=True, exist_ok=True)
    if not api.space_info(args.repo).private:
        raise ValueError('Refusing to upload private integration source to a public Space')
    for stage, url in urls.items():
        api.add_space_variable(args.repo, 'CONVFILL_' + stage + '_URL', url)
        api.add_space_secret(args.repo, 'CONVFILL_' + stage + '_API_KEY',
                             os.environ.get('CONVFILL_' + stage + '_API_KEY', os.environ['HF_TOKEN']))
    api.add_space_variable(args.repo, 'CONVFILL_REASONER_MODEL', os.environ.get('CONVFILL_REASONER_MODEL', 'nvidia/Gemma-4-31B-IT-NVFP4'))
    api.add_space_variable(args.repo, 'CONVFILL_STT_MODEL', os.environ.get('CONVFILL_STT_MODEL', 'Qwen/Qwen3-ASR-1.7B'))
    api.add_space_variable(args.repo, 'CONVFILL_LOG_CONTENT', '0')
    for name in ("CONVFILL_SEARCH_URL", "STARTUP_GREETING"):
        if name in os.environ:
            api.add_space_variable(args.repo, name, os.environ[name])
    for name in ("SERPER_API_KEY", "CONVFILL_SEARCH_API_KEY"):
        if os.environ.get(name):
            api.add_space_secret(args.repo, name, os.environ[name])
    with tempfile.TemporaryDirectory(prefix='convfill-space-') as temporary:
        target = Path(temporary)
        for name in ['Dockerfile', 'pyproject.toml', 'LICENSE', '.dockerignore']:
            shutil.copy2(root / name, target / name)
        for name in ['src', 'configs', 'scripts', 'web_demo/hf_convfill', 'web_demo/hf_interface', 'deploy']:
            shutil.copytree(root / name, target / name, ignore=shutil.ignore_patterns(
                '__pycache__', 'node_modules', '*.pyc', '.env', '*.log'))
        (target / 'README.md').write_text('---\ntitle: ConvFill Gemma Voice Demo\nemoji: 🎙️\ncolorFrom: blue\ncolorTo: green\nsdk: docker\napp_port: 7860\npinned: false\n---\n\nPrivate single-session ConvFill speech demo using smolagents model services.\n')
        commit = api.upload_folder(repo_id=args.repo, repo_type='space', folder_path=target,
                                   commit_message='Deploy hosted Gemma and ConvFill speech demo')
    print('Space:', args.repo, 'commit:', commit.oid)


if __name__ == '__main__':
    main()
