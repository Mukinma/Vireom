export function isCurrentWakeAttempt(snapshot, wakeAttemptId, wakingState = 'WAKING') {
  if (!snapshot || typeof snapshot !== 'object') {
    return false;
  }
  return snapshot.state === wakingState && snapshot.wakeAttemptId === wakeAttemptId;
}
