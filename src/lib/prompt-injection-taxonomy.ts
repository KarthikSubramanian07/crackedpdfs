export const PROMPT_INJECTION_MESSAGE_TYPES = [
  "instruction_override",
  "task_hijack",
  "policy_framing",
  "system_extraction",
  "refusal_suppression",
  "data_exfiltration",
  "agent_tool_manipulation",
  "summarization_steering",
] as const;

export type PromptInjectionMessageType =
  (typeof PROMPT_INJECTION_MESSAGE_TYPES)[number];

export const PROMPT_INJECTION_MESSAGE_TYPE_LABELS: Record<
  PromptInjectionMessageType,
  string
> = {
  instruction_override: "Instruction Override",
  task_hijack: "Task Hijack",
  policy_framing: "Policy Framing",
  system_extraction: "System Extraction",
  refusal_suppression: "Refusal Suppression",
  data_exfiltration: "Data Exfiltration",
  agent_tool_manipulation: "Agent Tool Manipulation",
  summarization_steering: "Summarization Steering",
};
