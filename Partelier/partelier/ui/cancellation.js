"use strict";
// Cancel must never wait behind the picker that it needs to stop.
window.PartelierCancellation = Object.freeze({
 create({busy, error, finished = () => {}}) {
  let generation = 0, tail = Promise.resolve(), count = 0, cancelling = false, confirmation;
  const cancelled = Object.freeze({cancelled:true});
  let release, signal = new Promise(resolve => { release = resolve; });
  const current = token => token === generation;
  const report = problem => { if (problem !== cancelled) error(problem); };
  function invalidate() {
   generation++; release(cancelled);
   signal = new Promise(resolve => { release = resolve; });
  }
  return Object.freeze({
   get cancelling() { return cancelling; },
   isCancelled: problem => problem === cancelled,
   confirm(snapshot) {
    if (confirmation && ["cancelled","created"].includes(snapshot.phase)
      && (snapshot.endedSessionId || snapshot.sessionId) === confirmation.sessionId) confirmation.resolve();
   },
   async wait(promise) {
    const token = generation, interruption = signal;
    const result = await Promise.race([promise, interruption]);
    if (!current(token) || result === cancelled) throw cancelled;
    return result;
   },
   run(task) {
    if (cancelling) return Promise.resolve();
    const token = generation;
    count++; busy(true, count);
    const running = tail.then(() => { if (current(token)) return task(); });
    tail = running.catch(problem => { if (current(token)) report(problem); });
    return tail.finally(() => {
     if (current(token)) { count--; busy(count > 0, count); finished(); }
    });
   },
   async cancel(task, sessionId) {
    if (cancelling) return;
    cancelling = true;
    invalidate();
    const confirmed = new Promise(resolve => { confirmation = {sessionId, resolve}; });
    tail = Promise.resolve(); count = 0;
    busy(true, count);
    // A terminal native push is authoritative even if Qt loses the Cancel ack.
    try { await Promise.race([task(), confirmed]); } catch (problem) { report(problem); }
    finally { confirmation = undefined; invalidate(); cancelling = false; busy(false, 0); }
   }
  });
 }
});
