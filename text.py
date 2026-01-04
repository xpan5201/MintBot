from openai import OpenAI

client = OpenAI(
    base_url="http://fgs6.bakamoe.com:9002/v1",
    api_key="any",
)

resp = client.chat.completions.create(
    model="./Qwen3-235B-A22B-Instruct-2507-NVFP4",
    messages=[
        {"role": "system", "content": "你是一个猫娘。"},
        {"role": "user", "content": "帮我写一个猫娘准则（200字左右）。"},
    ],
    temperature=0.7,
)

print(resp.choices[0].message.content)
