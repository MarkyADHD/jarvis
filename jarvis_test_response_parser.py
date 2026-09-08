
import jarvis_response_v2 as r

samples = [
    '<think>I should answer</think>{"mode":"chat","reply":"Hello, Sir.","steps":[]}',
    '```json\n{"answer":"This is fine.","steps":[]}\n```',
    'This is just a normal model answer, Sir.',
]

for sample in samples:
    print(r.parse_model_plan(sample, name="Sir"))
