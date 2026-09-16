// Release feedback must never obscure a new live decision after the catch.
export function passFeedbackActive(pass, time) {
  return pass.start<=time && time<Math.min(pass.start+12.5,
    Number.isFinite(pass.end)?pass.end:Infinity);
}
