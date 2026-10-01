# Operator Manual

For shop-floor operators using the **Shop-Floor Terminal**. You need a normal
Odoo login (username and password) given to you by your supervisor — there is
no separate PIN.

---

## 1. Logging In

1. Open the terminal's address on the shop-floor tablet (your supervisor sets
   this up once — it is the plant server's address followed by `/fmes/terminal`).
2. Enter your username and password.
3. You land directly on the terminal — you never see the regular Odoo desktop
   screen, and you don't need to.

You only see machines you are assigned to: either today's roster (if your
supervisor has scheduled you for the day) or your permanent machine
assignment. If neither is set, you can record on any active machine, but you
will still only ever see your own entries.

## 2. Recording Production

1. **Pick your machine** from the machine list shown on the terminal.
2. **Pick the shift** (morning / afternoon / night — whichever is running).
3. The terminal shows your assigned work order(s) for that machine and shift:
   target quantity and elapsed time.
4. Tap **Start** — this begins a live timer.
5. When you finish a run (or at the end of the shift), enter:
   - **Quantity produced**, using the on-screen numeric keypad
   - **Reject quantity**, if any pieces did not pass
6. Tap **Stop**, then **Submit**.

Your entry is now **submitted**, waiting for your supervisor to approve it.
Once approved, you cannot edit it — if you made a mistake, tell your
supervisor before they approve it, or ask them to reject it back to you.

## 3. Logging Downtime

If the machine stops for any reason — waiting for material, a breakdown, a
changeover, anything — log it as downtime instead of leaving it unrecorded:

1. Tap **Downtime** on the terminal.
2. Pick a reason from the list (grouped by category — e.g. Material,
   Breakdown, Changeover, Planned Maintenance).
3. If you pick **Other**, you must type a short remark — it cannot be left
   blank.
4. The downtime timer starts running immediately and keeps running until you
   tap **Stop**.

Some reasons (like a machine breakdown) automatically create a maintenance
request behind the scenes — you don't need to do anything extra; maintenance
will be notified.

Your downtime entry also goes to your supervisor for approval. If it's
rejected, it comes back to you to correct and resubmit.

## 4. Maintenance Checklists

If your machine has a scheduled preventive-maintenance checklist due, it
appears as a task you can open and complete: tick off each checklist line as
you do it, and submit the result. This does not replace a maintenance
request — a genuine breakdown is still logged as downtime (see above), which
raises its own request automatically.

## 5. Things to Know

- **You cannot see** costs, other departments' data, the production plan, or
  reports — the terminal is deliberately a small, focused screen.
- **An approved entry cannot be un-submitted by you.** If something needs
  correcting after approval, only a supervisor or plant manager can unlock it.
- **The terminal works one machine at a time.** If you operate more than one
  machine in a shift, switch machines from the picker rather than trying to
  run two timers at once.
