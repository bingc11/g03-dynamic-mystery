import { nanoid } from "nanoid";
import constate from "constate";

const SESSION_KEY = "MYSTERY_SESSION";

export const [SessionProvider, useSessionContext] = constate(({ scope }: { scope?: string } = {}) => {
  if (scope) return scope;
  // Check for a session key in local storage
  const localSessionId = localStorage.getItem(SESSION_KEY);
  if (localSessionId) {
    return localSessionId;
  } else {
    const newSessionId = nanoid();
    localStorage.setItem(SESSION_KEY, newSessionId);
    return newSessionId;
  }
});
