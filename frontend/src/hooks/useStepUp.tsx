import { useState } from 'react';
import { ApiError } from '../api/client';
import StepUpDialog from '../components/StepUpDialog';

/** Raised when the person closes the confirmation dialog; callers treat it as "nothing happened". */
export class StepUpCancelled extends Error {
  constructor() { super('Confirmation cancelled'); this.name = 'StepUpCancelled'; }
}

interface Pending { run: () => Promise<unknown>; resolve: (value: unknown) => void; reject: (cause: unknown) => void }

/**
 * `guard(action)` runs the action; when the server answers STEP_UP_REQUIRED it shows the code dialog and,
 * once confirmed, runs the same action again. Render `dialog` once near the top of the page.
 */
export function useStepUp() {
  const [pending, setPending] = useState<Pending | null>(null);

  async function guard<T>(action: () => Promise<T>): Promise<T> {
    try { return await action(); }
    catch (cause) {
      if (!(cause instanceof ApiError && cause.code === 'STEP_UP_REQUIRED')) throw cause;
      return new Promise<T>((resolve, reject) => setPending({ run: action, resolve: value => resolve(value as T), reject }));
    }
  }

  const dialog = pending && <StepUpDialog
    onConfirmed={() => { setPending(null); pending.run().then(pending.resolve, pending.reject); }}
    onCancel={() => { setPending(null); pending.reject(new StepUpCancelled()); }} />;
  return { guard, dialog };
}
