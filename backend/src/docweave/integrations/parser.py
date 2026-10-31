import asyncio, json, subprocess
from uuid import uuid4


async def container_parse(content, media_type):
    name = "docweave-parser-" + uuid4().hex
    command = ["docker", "run", "--rm", "--name", name, "-i", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=512m", "--memory-swap=512m", "--cpus=1",
        "--pids-limit=16", "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", "docweave-text-parser:3a", media_type]
    def parse():
        try:
            process = subprocess.run(command, input=content, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
            if process.returncode == 2:
                raise ValueError("Invalid text")
            if process.returncode:
                raise OSError("Parser unavailable")
            return json.loads(process.stdout)
        finally:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    return await asyncio.to_thread(parse)
