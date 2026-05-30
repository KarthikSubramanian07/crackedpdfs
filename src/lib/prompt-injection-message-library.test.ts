import test from "node:test";
import assert from "node:assert/strict";
import {
  PROMPT_INJECTION_MESSAGE_TYPES,
  type PromptInjectionMessageType,
} from "@/lib/prompt-injection-taxonomy";
import {
  RECOMMENDED_PROMPT_INJECTION_MESSAGES,
  RECOMMENDED_PROMPT_MESSAGE_COUNTS_BY_TYPE,
  TOTAL_RECOMMENDED_PROMPT_MESSAGE_COUNT,
} from "@/lib/prompt-injection-message-library";

test("recommended prompt injection library provides broad per-type coverage", () => {
  const counts = Object.fromEntries(
    PROMPT_INJECTION_MESSAGE_TYPES.map((messageType) => [messageType, 0])
  ) as Record<PromptInjectionMessageType, number>;

  const uniqueKeys = new Set<string>();
  for (const message of RECOMMENDED_PROMPT_INJECTION_MESSAGES) {
    counts[message.messageType] += 1;
    uniqueKeys.add(`${message.messageType}::${message.name}`);
    assert.equal(message.isActive, true);
    assert.ok(message.content.trim().length > 0);
  }

  assert.equal(
    uniqueKeys.size,
    RECOMMENDED_PROMPT_INJECTION_MESSAGES.length,
    "recommended messages should have unique type/name keys"
  );
  assert.equal(
    TOTAL_RECOMMENDED_PROMPT_MESSAGE_COUNT,
    RECOMMENDED_PROMPT_INJECTION_MESSAGES.length
  );
  assert.ok(
    TOTAL_RECOMMENDED_PROMPT_MESSAGE_COUNT >= 100,
    "recommended library should contain at least 100 concrete messages"
  );

  for (const messageType of PROMPT_INJECTION_MESSAGE_TYPES) {
    assert.equal(
      counts[messageType],
      RECOMMENDED_PROMPT_MESSAGE_COUNTS_BY_TYPE[messageType]
    );
    assert.ok(
      counts[messageType] >= 12,
      `${messageType} should have at least 12 concrete messages`
    );
  }
});
