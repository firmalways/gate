"""Use FirmAlways Gate with the official OpenAI Python SDK: only base_url changes.

    pip install openai
    firmalways-gate echo-upstream --port 8788 &
    FIRMALWAYS_GATE_API_KEY=demo-key firmalways-gate serve --policy examples/policy.demo.toml &
    python examples/openai_sdk_demo.py
"""

import os

from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1", api_key=os.environ.get("FIRMALWAYS_GATE_API_KEY", "demo-key"))
prompt = "สรุปเรื่องร้องเรียนของนายสมชาย ใจดี บัตร 1101700203611 โทร 0812345678"

reply = client.chat.completions.create(model="echo", messages=[{"role": "user", "content": prompt}])
print("non-stream:", reply.choices[0].message.content)

stream = client.chat.completions.create(model="echo", messages=[{"role": "user", "content": prompt}], stream=True)
print("stream:    ", "".join(chunk.choices[0].delta.content or "" for chunk in stream if chunk.choices))
