TITLE
Fine-tune vs RAG vs prompt: measured on a legacy SQL task

ROLE
AI Engineer: evaluation, fine-tuning and cost measurement

DESCRIPTION
Before recommending fine-tuning, I measured it. On a synthetic legacy billing and inventory schema (PostgreSQL, with documented defects), I tested 46 natural-language questions, scored by exact match of the returned result. Results: 27B model 45.7%; with business rules in the prompt 50.0%; with rules retrieved per question (RAG) 41.3%; 7B base 37.0%; 7B with LoRA fine-tuning 37.0%. The fine-tune changed the SQL but not the correct answers, so the decision was: the prompt is enough, no fine-tuning. I also measured speed and cost on 50 queries: a local 27B model (MLX, 4-bit) took a median of 52 s per answer, while Claude Haiku 5.5 via API took 4 s, at about $0.47 per 1,000 queries. Limits: 46 questions, one run each; the differences are not statistically significant, so the value is the method and the decision rule. Code, data and results (MIT license): github.com/mcorona/AI-projects-llm-internals

LINK
https://github.com/mcorona/AI-projects-llm-internals
