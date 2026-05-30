/** @jsxImportSource preact */
// JudgeSelect — segmented control for the eval judge backend.
//
// LOCAL · NIM (the warm resident brain) vs OpenRouter (cloud frontier).
// OpenRouter is disabled + greyed when there's no API key. When the active
// eval prompt is deterministically scored, the control renders muted/inert
// with a "scored instantly — no judge" note, since the backend only matters
// for judge-backed families (patent A / D-oa / open-ended C / E) and
// free-prompt quality grading.

export default function JudgeSelect({ value, onChange, availability, deterministic }) {
  const av = availability || {};
  if (deterministic) {
    return (
      <span class="judge-select judge-select--muted" title="Deterministic scorer — graded instantly, no judge model, no cost">
        ⚡ scored instantly — no judge used
      </span>
    );
  }
  const orDisabled = !av.openrouter_available;
  return (
    <span class="judge-select" role="radiogroup" aria-label="Judge backend">
      <span class="judge-select__label">Judge</span>
      <button
        type="button"
        class={`judge-select__seg ${value === 'local' ? 'is-active' : ''}`}
        aria-pressed={value === 'local'}
        disabled={!av.local_available}
        title={av.local_available ? 'Grade with the warm resident brain (free, local)' : 'No resident brain configured'}
        onClick={() => onChange('local')}
      >
        local · NIM
      </button>
      <button
        type="button"
        class={`judge-select__seg ${value === 'openrouter' ? 'is-active' : ''} ${orDisabled ? 'is-disabled' : ''}`}
        aria-pressed={value === 'openrouter'}
        disabled={orDisabled}
        title={orDisabled ? 'Set OPENROUTER_API_KEY to grade with a cloud frontier model' : 'Grade with a cloud frontier model'}
        onClick={() => !orDisabled && onChange('openrouter')}
      >
        OpenRouter
      </button>
    </span>
  );
}
