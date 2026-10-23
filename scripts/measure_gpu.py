"""Sample whole-replica GPU memory from smolagents' OpenMetrics API."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--output', default='/tmp/convfill-gpu-measurements.json')
    args = parser.parse_args()
    names = ['reachy-s2s-llm-01', 'convfill-talker', 'reachy-s2s-stt-01', 'reachy-s2s-tts-01']
    result = {name: {'samples': 0, 'max_sampled_bytes': None, 'replicas': {}} for name in names}
    def sample(name):
        try:
            request = urllib.request.Request('https://api.endpoints.huggingface.cloud/v2/endpoint/smolagents/' + name + '/open-metrics',
                                            headers={'Authorization': 'Bearer ' + os.environ['HF_TOKEN']})
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode()
            values = re.findall(r'^gpu_memory_used_bytes\{replica_id="([^"]+)"\}\s+([\d.e+]+)', body, re.M)
            return name, values
        except Exception:
            return name, []
    deadline = time.monotonic() + args.seconds
    with ThreadPoolExecutor(4) as pool:
        while time.monotonic() < deadline:
            for name, values in pool.map(sample, names):
                for replica, value in values:
                    value = float(value)
                    record = result[name]
                    record['samples'] += 1
                    record['max_sampled_bytes'] = max(record['max_sampled_bytes'] or 0, value)
                    record['replicas'][replica] = max(record['replicas'].get(replica, 0), value)
            Path(args.output).write_text(json.dumps({'namespace': 'smolagents', 'kind': 'sampled whole-replica memory; not allocator high-water mark',
                                                     'services': result}, indent=2) + '\n')
            time.sleep(1)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
