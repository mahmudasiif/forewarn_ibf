/**
 * Capability checks for role-gated parts of the UI.
 *
 * Authentication is not built yet — every check below returns true, so the
 * portal behaves exactly as it does today. The point of having this now is
 * that the gated parts of the UI are written against it from the start, so
 * turning the gate on later is a change to this one file plus the login that
 * populates it, not a hunt through every screen for the things that should
 * have been restricted.
 *
 * When auth lands: replace `useCurrentRoles` with a read from the session, and
 * everything already wrapped in `useCan` starts enforcing. Nothing else moves.
 */

/** A role a signed-in user can hold. Mirrors what the API will issue. */
export type Role = "admin" | "analyst" | "operator" | "viewer";

/**
 * A thing a user may be allowed to do. Named after the action, not the screen,
 * so the same capability can gate a control in more than one place.
 */
export type Capability =
  /** Set the trigger parameter and threshold on a model screen. Deciding what
   *  counts as a trigger is an operational judgement, not a reading task. */
  | "ccm:set-trigger"
  /** Start a new model run from uploaded simulation files. */
  | "ccm:run-model"
  /** Drag a stored cyclone's track to a new path and re-run the model on it. */
  | "ccm:simulate-track";

/** Who may do what, once roles are real. */
const CAPABILITIES: Record<Capability, readonly Role[]> = {
  "ccm:set-trigger": ["admin", "analyst", "operator"],
  "ccm:run-model": ["admin", "analyst"],
  "ccm:simulate-track": ["admin", "analyst"],
};

/**
 * The signed-in user's roles.
 *
 * Until there is a session, everyone is an admin — the portal is behind HTTP
 * basic auth at the proxy and has no public access, so this does not expose
 * anything. It is a placeholder with a single obvious place to replace.
 */
function useCurrentRoles(): readonly Role[] {
  return ["admin"];
}

/** Whether the current user may do `capability`. */
export function useCan(capability: Capability): boolean {
  const roles = useCurrentRoles();
  const allowed = CAPABILITIES[capability];
  return roles.some((role) => allowed.includes(role));
}
