-- Session rule engine phases 2 and 3 (operator 2026-09-26): the ML sleeve's price-confirmation watches and the gap-fade
-- closing exit become intents of the one session tick, replacing the combo_confirm (every 2 min) and combo_gap_exit (15:50) jobs.

-- ens4 arms up to four watches on one name (one per confirmation rule): one live intent per name, kind AND rule.
DROP INDEX IF EXISTS idx.order_intent_one_live;
CREATE UNIQUE INDEX order_intent_one_live ON idx.order_intent (book, code, kind, COALESCE(ref->>'rule', ''))
    WHERE status IN ('armed', 'triggered', 'ticket_issued');

-- 'carried': fired, but its job was done without a ticket of its own (an ens4 share already bought by an earlier rule, a dust
-- share carried to the next rule, a gap exit already on today's exit ticket). It still counts as triggered for the ensemble.
ALTER TABLE idx.order_intent DROP CONSTRAINT IF EXISTS order_intent_status_check;
ALTER TABLE idx.order_intent ADD CONSTRAINT order_intent_status_check
    CHECK (status IN ('armed', 'triggered', 'ticket_issued', 'filled', 'carried', 'expired', 'cancelled'));

CREATE INDEX IF NOT EXISTS order_intent_ml_signal ON idx.order_intent (book, code, (ref->>'signal_date')) WHERE kind = 'ml_confirm';

-- the watches that are still pending move over as armed intents (same level, window, expiry); the combo_watch row is closed
-- with a pointer, so the table keeps the history and nothing is watched twice
WITH moved AS (
    INSERT INTO idx.order_intent (book, sleeve, code, side, kind, trigger, ref, expires_on, created_at)
    SELECT w.book, w.sleeve, w.code, 'buy', 'ml_confirm',
           jsonb_build_object('type', 'price_at_or_above', 'level', w.level_price, 'after', '08:58', 'before', '15:50'),
           jsonb_build_object('signal_date', w.signal_date::text, 'ref_price', w.ref_price, 'level_price', w.level_price,
                              'e_bps', w.e_bps, 'cost_bps', w.cost_bps, 'rule', COALESCE(w.rule, '+5/10'), 'size_frac', COALESCE(w.size_frac, 1),
                              'watch_id', w.id),
           w.until_date, w.created_at
      FROM idx.combo_watch w
     WHERE w.status = 'pending'
    RETURNING id, (ref->>'watch_id')::bigint AS watch_id
), ev AS (
    INSERT INTO idx.order_intent_event (intent_id, from_status, to_status, note, actor)
    SELECT id, NULL, 'armed', 'moved from combo_watch #' || watch_id, 'migration-0050' FROM moved
    RETURNING intent_id
)
UPDATE idx.combo_watch w SET status = 'cancelled', note = 'moved to order_intent #' || m.id, updated_at = now()
  FROM moved m WHERE w.id = m.watch_id;
