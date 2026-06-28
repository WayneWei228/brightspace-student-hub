# Crowdmark API Reference

Base URL: `https://app.crowdmark.com`

Crowdmark is an Ember.js SPA. All endpoints discovered via CDP network interception.

## List All Assignments

```
GET /api/v2/student/assignments
```

Returns JSON:API format with `data[]`. Each assignment:

| Field | Description |
|---|---|
| `attributes.name` | Assignment name |
| `attributes.normalized-points` | Score as fraction of 1.0 (e.g. 0.786) |
| `attributes.total-points` | Max score |
| `attributes.submitted-at` | ISO 8601 UTC or null |
| `attributes.marks-sent-at` | ISO 8601 UTC or null (grades released) |
| `attributes.due` | ISO 8601 UTC due date |
| `relationships.course.data.id` | Course ID |
| `relationships.scores.data[0].id` | score_uuid for per-question grades |

## Submission Status Logic

```python
def get_status(submitted_at, marks_sent_at, norm_pts, total_pts):
    if submitted_at is None:
        return "Not submitted"
    elif marks_sent_at is None:
        return "Submitted, awaiting grade"
    else:
        score = norm_pts * total_pts if norm_pts and total_pts else 0
        return f"Graded: {score:.1f}/{total_pts}"
```

Do NOT use labels like "drafting" — only use what the API returns.

## Per-Question Grades and Feedback

```
GET /api/v1/student/results/{score_uuid}
```

Response includes:
- `evaluations[]` — `{question_id, points_earned, points_available}`
- `annotations[]` — `{type, metadata.text, metadata.points}`
  - `type == "CommentAnnotation"` → instructor text feedback
  - `metadata.points` can be null — still report the annotation

Report ALL `CommentAnnotation` entries, even if `metadata.points` is null.

## Course-Assignment Association

The `/api/v2/student/assignments` endpoint returns all assignments across all courses. Each assignment's `relationships.course.data.id` links it to a course. Use this to group assignments by course — do not assume which assignments belong to which course.

Some institutions share exam-masters across multiple courses; the API assigns each to exactly one course ID.

## Common Pitfall

`normalized_points = 0` with `submitted_at = null` = not submitted (score 0 by default). This is NOT the same as a submitted assignment that earned 0 points. Check `submitted_at` first.
