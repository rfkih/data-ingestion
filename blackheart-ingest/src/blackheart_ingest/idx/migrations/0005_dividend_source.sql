-- Dividend rows can come from disclosures (amount in PDF, phase 3) or from Yahoo's dated events (secondary source).
ALTER TABLE idx.dividend ADD COLUMN source TEXT NOT NULL DEFAULT 'announcement';
