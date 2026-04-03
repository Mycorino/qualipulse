# AutoInterview — QA Test Checklist

> Run through this checklist before every release.
> Test environment: `http://localhost:5173` (frontend) + `http://localhost:8000` (backend)

---

## Auth flows

- [ ] Sign up with new email → 201 returned, welcome email logged to console
- [ ] Sign up with existing email → 409 error shown in UI
- [ ] Sign up with short/invalid password → validation error shown
- [ ] Login with correct credentials → access token + refresh token returned and stored in localStorage
- [ ] Login with wrong password → 401 shown, no account lockout, can try again
- [ ] Login 11+ times rapidly → 429 rate limit kicks in, Retry-After header present
- [ ] Navigate to `/forgot-password` → form shown
- [ ] Request password reset → console logs reset URL (dev mode)
- [ ] Visit reset link from console → `/reset-password?token=...` loads correctly
- [ ] Submit new password via reset link → password updated, success message shown
- [ ] Login with old password after reset → 401
- [ ] Login with new password after reset → success
- [ ] Use expired reset token (wait >1h or manually expire) → 400 error shown
- [ ] Use already-used reset token → 400 error shown
- [ ] JWT access token expires → refresh token auto-used, no logout, request retried
- [ ] `GET /auth/me` with no token → 401
- [ ] `GET /auth/me` with invalid/tampered token → 401
- [ ] Logout / clear localStorage → redirect to login on next protected request

---

## Project management

- [ ] Create project via 4-step wizard (Brief → Objective → Scope → Questionnaire)
- [ ] Upload a .txt or .md file in Step 1 → brief summary populated
- [ ] Click "Generate objective" → AI fills objective and 3 learning goals
- [ ] Click "Suggest scope" → AI fills audience, duration, language
- [ ] Click "Generate questions" → AI populates full interview guide
- [ ] Manually edit a guide question text → change saved correctly
- [ ] Add interview note and desired learning to a question → persists on refresh
- [ ] Deprecate a question → removed from live interview, shown as deprecated in Setup tab
- [ ] Un-deprecate a question → returns to active guide
- [ ] Add screening question with at least one disqualifying option in Setup tab
- [ ] Reorder / edit screening question options inline
- [ ] Toggle interview link active → inactive → active again
- [ ] Create a second interview link → both appear in Overview
- [ ] CSV export downloads file with correct column headers
- [ ] Delete a project → removed from dashboard, 404 on subsequent fetch
- [ ] Navigate away mid-wizard → data not unexpectedly persisted

---

## Participant interview flow

### Consent
- [ ] Visit interview URL with valid token → consent screen shown with project name and duration
- [ ] Decline consent → "No problem" screen, form never shown, no participant record created
- [ ] Accept consent → landing form shown

### Landing & resume
- [ ] Enter email that has an in-progress session → resume card shown with covered topics and elapsed time
- [ ] Click "Continue my interview" → picks up from last question, elapsed time restored
- [ ] Click "Start a new interview" from resume card → screening / new interview begins
- [ ] Enter email with no prior session → no resume card, normal flow
- [ ] Refresh landing page mid-session (session storage resume) → resume banner appears at top
- [ ] Click "Resume →" from banner → interview continues
- [ ] Click "Start over" from banner → session cleared, starts fresh

### Screening
- [ ] Enter email, click Start → fetch screening questions → first question shown with progress bar
- [ ] Select option on question 1 of 3 → progress bar advances, question 2 shown
- [ ] Click back → previous question shown with previous answer still selected
- [ ] Select disqualifying option on final screening question → disqualified screen shown
- [ ] Select non-disqualifying options throughout → interview starts
- [ ] Project with no screening questions → interview starts immediately after landing

### Interview
- [ ] First question TTS plays automatically after start
- [ ] Mute button stops TTS playback
- [ ] Unmute → TTS does not replay, mute state visible
- [ ] Progress label shows "Q1 of 5" (not raw turn count)
- [ ] Time remaining shows and counts down in real-time
- [ ] Time warning colour change at ~75% elapsed
- [ ] Time critical colour change at ~90% elapsed
- [ ] Click record button → recording state (pulsing animation, "Tap to stop")
- [ ] Click stop → processing spinner shown
- [ ] Processing completes → next question shown, TTS plays
- [ ] Follow-up turn shows "Follow-up · Q2 of 5"
- [ ] Mic permission denied → error UI shown with refresh button
- [ ] Submit fails on network error → error banner shown (check error does not lose blob)
- [ ] Multiple turns → Claude eventually returns `is_complete: true` → complete screen

### Completion
- [ ] Complete screen shown with checkmark
- [ ] Session storage cleared on complete
- [ ] Navigating back to interview URL shows consent screen again (not in-progress state)

---

## Researcher analysis

### Responses tab
- [ ] Participant list shows display name, status, demographics, turn count
- [ ] Quality badge shown (low / fair / good / strong) based on response length heuristic
- [ ] Click participant row → transcript viewer opens
- [ ] All turns shown in order (question + answer pairs)
- [ ] `is_follow_up` turns visually distinguished
- [ ] Edit transcript turn text → save → refresh → edit persists, `manually_edited` flag shown
- [ ] AI Quality Check button → POST to `/participants/{pid}/quality` → assessment panel opens with score, summary, strengths, issues

### Analysis tab
- [ ] Click "Generate analysis" → status shows "generating"
- [ ] Poll until "ready" → analysis report appears
- [ ] Report shows: executive summary, themes (with quotes), JTBDs, tensions, recommendations
- [ ] Segment heatmap appears after analysis is ready
- [ ] Heatmap shows profession / age_range / country breakdowns
- [ ] Filter analysis by segment → re-run with filtered participants
- [ ] Analysis with 0 completed participants → 400 error shown, not crash

### Codebook
- [ ] Create a code with name + colour → appears in codebook
- [ ] Select text in transcript → assign code → tag appears highlighted
- [ ] Tags list shows participant name and turn context
- [ ] Delete a tag → removed from transcript
- [ ] Rename a code → all tags reflect new name
- [ ] Delete a code → associated tags deleted

### Memos
- [ ] Add a general memo → persists on refresh
- [ ] Add a theme-linked memo → appears under correct theme in analysis
- [ ] Edit memo content → saved
- [ ] Delete memo → removed

### Export
- [ ] CSV export button downloads file
- [ ] CSV contains all participants + all turns for completed participants
- [ ] Empty-turn participants still appear with a row (no turns column data)

---

## Security checks

- [ ] `GET /projects/` without Authorization header → 401
- [ ] `GET /projects/{id}` belonging to another company → 404 (not 403 or 200)
- [ ] `GET /interview/{token}` with inactive link token → 404
- [ ] `POST /interview/{token}/{pid}/respond` with completed participant → 400
- [ ] Audio upload with Content-Length > 50MB → 413
- [ ] Login 11+ times in quick succession → 429, Retry-After header present
- [ ] Response headers include `X-Frame-Options: DENY`
- [ ] Response headers include `X-Content-Type-Options: nosniff`
- [ ] Response headers include `X-XSS-Protection: 1; mode=block`
- [ ] Response headers include `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] `GET /audio/../../../etc/passwd` (or similar) → 403 (directory traversal blocked)
- [ ] CORS blocks requests from unknown origins (verify in prod config with `ALLOWED_ORIGINS` set)

---

## Account & billing

- [ ] Navigate to `/account` → Profile tab shown with name and email
- [ ] Navigate to Billing tab → current plan shown (Free by default)
- [ ] `/billing/plans` returns 4 tiers with correct prices and limits
- [ ] `/billing/status` returns `tier`, `tier_name`, `status`, `limits`, `usage`
- [ ] Click "Upgrade to Starter" without Stripe configured → "Billing not configured" message (503)
- [ ] `/forgot-password` page renders correctly
- [ ] `/reset-password?token=abc123` page renders correctly
- [ ] Entering mismatched or too-short password on reset → validation error

---

## Mobile (viewport 375px wide)

- [ ] Interview consent screen fully readable and usable
- [ ] Landing form fields accessible and usable with soft keyboard
- [ ] Screening question options tap-friendly (no tiny hit targets)
- [ ] Record button large enough to tap accurately
- [ ] Progress bar and time remaining visible
- [ ] Complete screen renders cleanly
- [ ] Dashboard project list readable
- [ ] Project detail tabs accessible (no horizontal overflow)
- [ ] Transcript viewer scrollable with long responses

---

## Safari-specific (audio recording)

- [ ] `MediaRecorder` falls back to `audio/mp4` on Safari
- [ ] File extension correctly set to `.mp4` in FormData upload
- [ ] TTS audio plays on Safari without autoplay block (after user gesture)
- [ ] Recording and submission complete successfully end-to-end on Safari iOS

---

## Edge cases & regression

- [ ] Project with no guide questions → start interview → Claude handles gracefully
- [ ] Participant with 0 turns → transcript viewer shows empty state, no crash
- [ ] Very long participant response (> 3 min of speech) → STT handles without timeout
- [ ] Analysis triggered twice rapidly → second trigger does not duplicate results
- [ ] Deleting a code that has tags → tags also deleted, no orphan data
- [ ] Screening with 0 questions → participant created immediately, no screening phase
- [ ] Old project (pre-screening-question schema) → `screening_questions ?? []` guard prevents crash
