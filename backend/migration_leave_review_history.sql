CREATE TABLE IF NOT EXISTS leave_review_history (
    id INTEGER NOT NULL AUTO_INCREMENT,
    leave_request_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    comment VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_leave_review_history_request_created (leave_request_id, created_at),
    CONSTRAINT fk_leave_review_history_request
        FOREIGN KEY (leave_request_id) REFERENCES leave_requests (id),
    CONSTRAINT fk_leave_review_history_reviewer
        FOREIGN KEY (reviewer_id) REFERENCES users (id)
) ENGINE=InnoDB;

INSERT INTO leave_review_history (
    leave_request_id, reviewer_id, action, comment, created_at
)
SELECT
    requests.id,
    requests.reviewed_by,
    requests.status,
    requests.review_comment,
    COALESCE(requests.updated_at, requests.created_at)
FROM leave_requests AS requests
WHERE requests.status IN ('approved', 'rejected')
  AND requests.reviewed_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM leave_review_history AS history
      WHERE history.leave_request_id = requests.id
  );
