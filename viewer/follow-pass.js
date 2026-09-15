// Replay camera state only: never contributes inputs to the predictive models.
export function followPass(state, player, flight, frame) {
  const continuous = state && frame >= state.frame && frame - state.frame <= 10;
  let pending = continuous && state.player === player ? state.pending : null;
  if (player == null)
    return { player: null, pending: null, frame, ball: false };
  if (flight?.passer === player) pending = flight;
  if (pending && frame >= pending.end) {
    player = pending.receiver ?? player;
    pending = null;
  }
  return {
    player,
    pending,
    frame,
    ball: !!pending && frame >= pending.start && frame < pending.end,
  };
}
