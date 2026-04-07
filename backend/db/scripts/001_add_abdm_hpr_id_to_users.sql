-- Migration: Add ABDM HPR ID column to users table
-- Purpose: Store ABDM Healthcare Professionals Registry ID for doctor verification
-- Date: 2026-04-07

-- Add the column (nullable to not break existing doctor users)
ALTER TABLE users
ADD COLUMN IF NOT EXISTS abdm_hpr_id VARCHAR(100);

-- Add an index for faster lookups during login
CREATE INDEX IF NOT EXISTS idx_users_abdm_hpr_id ON users (abdm_hpr_id)
WHERE abdm_hpr_id IS NOT NULL;

-- Add a comment for documentation
COMMENT ON COLUMN users.abdm_hpr_id IS 'ABDM Healthcare Professionals Registry ID for doctor verification';
