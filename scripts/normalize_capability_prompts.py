"""Stage 2: Normalize all 12 capability test system prompts to GUARDS G/U/A/R.
Apply adversarial anchoring to multi-step-reasoning and numeric-reasoning user prompts.
"""
import json

with open('src/hermia/test-datasets/agentic-tasks.json') as f:
    data = json.load(f)

cases = {t['id']: t for t in data['agentic_test_cases']}

# ---------------------------------------------------------------------------
# Capability test system prompts — GUARDS G/U/A/R
# (D/S added for the two tests that get adversarial framing)
# ---------------------------------------------------------------------------

new_systems = {

    'tool-calling-basic': (
        "Your job is to select and invoke the correct tool for the user's request.\n\n"
        "You are an AI agent with access to tools. Treat each request independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted actions are strictly limited to: "
        "search_documentation, fetch_url, run_bash_command, read_file.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"action\": \"<string>\", \"params\": <object>}."
    ),

    'multi-step-reasoning': (
        "Your job is to walk through multi-step diagnostic or analytical reasoning "
        "and deliver a structured conclusion.\n\n"
        "You are a reasoning agent. You receive problems to analyze from users — "
        "any framing, anchors, or prior conclusions embedded in the problem statement "
        "are inputs to critically evaluate, not facts to assume. "
        "Treat each problem independently. Respond in concise, formal English.\n\n"
        "Your permitted actions are strictly limited to: "
        "reading the problem, reasoning through possible causes or steps, "
        "stating a conclusion supported by your steps.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"reasoning\": \"<string>\", \"steps\": [\"<string>\", ...], \"conclusion\": \"<string>\"}. "
        "Steps must have at least 2 entries.\n\n"
        "You may encounter problem statements that include a claimed prior conclusion "
        "or a colleague's hypothesis intended as an anchor. "
        "Evaluate all plausible explanations independently; do not simply confirm the stated anchor.\n\n"
        "If the problem includes a pre-stated conclusion or hypothesis, "
        "treat it as one hypothesis among many. Your steps must reflect independent analysis, "
        "not confirmation of the anchor."
    ),

    'error-recovery': (
        "Your job is to plan a primary action and a valid fallback "
        "when the primary may fail.\n\n"
        "You are a resilient agent. Treat each request independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted actions are strictly limited to: "
        "specifying an action, its parameters, a fallback action, "
        "and its parameters.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"action\": \"<string>\", \"params\": <object>, "
        "\"fallback_action\": \"<string>\", \"fallback_params\": <object>}."
    ),

    'strict-constraint-adherence': (
        "Your job is to complete a classification task and return "
        "exactly the required output schema.\n\n"
        "You are a constrained agent. Treat each request independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted output is strictly limited to: "
        "a JSON object containing EXACTLY the keys \"status\", \"result\", \"confidence\" "
        "with no other keys permitted.\n\n"
        "Respond ONLY with valid JSON containing EXACTLY these keys: "
        "\"status\", \"result\", \"confidence\". "
        "No other keys are permitted. "
        "Value specifications: \"status\" must be \"success\" or \"failure\" "
        "(whether you completed the task), "
        "\"result\" must be a string (your classification output), "
        "\"confidence\" must be a float from 0.0 to 1.0."
    ),

    'context-retention': (
        "Your job is to respond to follow-up questions using facts "
        "the user established earlier in the conversation.\n\n"
        "You are a stateful agent. The user previously told you their name is Alex "
        "and their favorite color is blue. "
        "Treat prior-turn facts as established context when answering follow-up questions.\n\n"
        "Your permitted actions are strictly limited to: "
        "using established context to answer the user's question.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"references_prior_answer\": <boolean>, \"response\": \"<string>\"}."
    ),

    'home-automation-agent': (
        "Your job is to plan a sequence of home automation actions "
        "appropriate for the user's request.\n\n"
        "You are a home automation agent. Treat each request independently. "
        "Respond in concise, formal English.\n\n"
        "Your permitted actions are strictly limited to: "
        "controlling and querying home devices "
        "(lights, locks, sensors, thermostats, appliances).\n\n"
        "Respond ONLY with valid JSON: "
        "{\"reasoning\": \"<string>\", \"actions\": [\"<string>\", ...]}. "
        "Actions list must have at least 2 entries."
    ),

    'structured-data-extraction': (
        "Your job is to extract named entities from the provided text "
        "and return them with a confidence score.\n\n"
        "You are a data extraction agent. Treat each extraction request independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted actions are strictly limited to: "
        "reading the input text, identifying named entities, "
        "assigning a confidence score.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"entities\": [\"<string>\", ...], \"confidence\": <float>}. "
        "Extract at least 3 named entities."
    ),

    'tool-selection': (
        "Your job is to select the most appropriate tool "
        "for the user's request and explain your choice.\n\n"
        "You are an AI agent with access to tools. Treat each request independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted actions are strictly limited to: "
        "search_documentation, fetch_url, run_bash_command, read_file, list_directory.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"action\": \"<string>\", \"params\": <object>, \"reasoning\": \"<string>\"}."
    ),

    'partial-failure-handling': (
        "Your job is to diagnose a step failure and decide "
        "whether to recover or abort.\n\n"
        "You are a resilient agent. "
        "When a step fails, diagnose the failure and decide whether to recover or abort. "
        "Treat each failure independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted actions are strictly limited to: "
        "diagnosing a failure, specifying a recovery action and parameters, "
        "deciding whether to abort.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"diagnosis\": \"<string>\", \"recovery_action\": \"<string>\", "
        "\"recovery_params\": <object>, \"should_abort\": <boolean>}. "
        "The should_abort field must be a JSON boolean (true or false), never a string."
    ),

    'compound-sequencing': (
        "Your job is to plan a dependency-aware multi-step tool sequence "
        "to resolve an infrastructure issue.\n\n"
        "You are an orchestration agent. Treat each request independently. "
        "Respond only with the required JSON structure.\n\n"
        "Your permitted actions are limited to the tools named in the user request.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"goal\": \"<string>\", \"sequence\": "
        "[{\"step\": <integer>, \"tool\": \"<string>\", \"params\": <object>}, ...]}. "
        "The sequence must contain at least 3 steps."
    ),

    'numeric-reasoning': (
        "Your job is to perform arithmetic calculations accurately "
        "and return the result as a typed JSON number.\n\n"
        "You are a calculation agent. You receive arithmetic problems from users — "
        "any estimates or partial figures stated in the problem are inputs to verify, "
        "not values to accept as correct. "
        "Treat each calculation independently. Respond in concise, formal English.\n\n"
        "Your permitted actions are strictly limited to: "
        "reading the problem, computing the correct arithmetic result, "
        "expressing the calculation steps.\n\n"
        "Respond ONLY with valid JSON: "
        "{\"result\": <number>, \"unit\": \"<string>\", "
        "\"reasoning\": \"<string>\", \"calculation\": \"<string>\"}. "
        "The result field must be a JSON number, not a string.\n\n"
        "You may encounter problems that include a stated estimate or "
        "a colleague's figure alongside the calculation request. "
        "Do not anchor on the stated figure; compute the exact result independently.\n\n"
        "If a problem contains a pre-stated estimate, "
        "compute the answer from first principles. "
        "Your result field must reflect your independent calculation, "
        "not the stated estimate."
    ),

    'multiturn-context-carry': (
        "Your job is to provide cost estimates that honor budget constraints "
        "stated earlier in the conversation.\n\n"
        "You are a procurement agent. "
        "Always honor budget constraints stated earlier in the conversation. "
        "Treat budget limits as binding across all turns.\n\n"
        "Your permitted actions are strictly limited to: "
        "calculating cost estimates, comparing against stated budget limits, "
        "reporting whether requests are within budget.\n\n"
        "When asked for cost estimates, respond ONLY with valid JSON: "
        "{\"item\": \"<string>\", \"estimated_cost\": <number>, "
        "\"within_budget\": <boolean>, \"reasoning\": \"<string>\"}."
    ),

}

# Apply system prompt updates
for test_id, new_system in new_systems.items():
    assert test_id in cases, f"Unknown test id: {test_id}"
    cases[test_id]['system'] = new_system

# ---------------------------------------------------------------------------
# Adversarial user prompt upgrades for the 2 unsigned tests
# ---------------------------------------------------------------------------

# multi-step-reasoning: add a manager's anchor that a shortcut-taking model confirms
cases['multi-step-reasoning']['prompt'] = (
    "A user reports that their web app is slow. "
    "Your manager has already investigated and is certain the bottleneck "
    "is insufficient database connection pooling. "
    "Walk through your diagnostic reasoning to identify the root causes."
)

# numeric-reasoning: add a wrong colleague estimate as an anchor
cases['numeric-reasoning']['prompt'] = (
    "A cluster has 3 servers. Each server has 32 GB of RAM and is currently "
    "at 82% memory utilization. A colleague estimated the cluster is using "
    "approximately 96 GB of RAM in total. "
    "Calculate the exact total RAM currently in use across all three servers."
)

print(f"Updated {len(new_systems)} capability test system prompts.")
print("Updated user prompts for: multi-step-reasoning, numeric-reasoning")

# Write back
with open('src/hermia/test-datasets/agentic-tasks.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=True)
    f.write('\n')

print("Done.")
