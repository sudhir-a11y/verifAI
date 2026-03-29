<?php

declare(strict_types=1);

require_once __DIR__ . '/config/db.php';

header('Content-Type: application/json; charset=utf-8');

function env_or_default(string $name, string $default = ''): string
{
    $val = getenv($name);
    if ($val === false || trim((string)$val) === '') {
        return $default;
    }
    return trim((string)$val);
}

function out_json(int $status, array $payload): void
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function map_recommendation(string $raw): ?string
{
    $v = strtolower(trim($raw));
    if ($v === '') {
        return null;
    }
    if (strpos($v, 'inadmiss') !== false || strpos($v, 'reject') !== false || strpos($v, 'not justified') !== false) {
        return 'reject';
    }
    if (strpos($v, 'admiss') !== false || strpos($v, 'approve') !== false || strpos($v, 'justified') !== false || strpos($v, 'payable') !== false) {
        return 'approve';
    }
    if (strpos($v, 'query') !== false || strpos($v, 'need more') !== false || strpos($v, 'manual') !== false) {
        return 'need_more_evidence';
    }
    return null;
}

function infer_recommendation(array $caseRow, ?array $analysisRow): ?string
{
    if ($analysisRow !== null) {
        $fromAdmission = strtolower(trim((string)($analysisRow['admission_required'] ?? '')));
        if ($fromAdmission === 'yes') return 'approve';
        if ($fromAdmission === 'no') return 'reject';

        $fromReport = map_recommendation((string)($analysisRow['report_html'] ?? ''));
        if ($fromReport) return $fromReport;
    }

    $fromFinalStatus = map_recommendation((string)($caseRow['final_status'] ?? ''));
    if ($fromFinalStatus) return $fromFinalStatus;

    return null;
}

function normalize_claim_status(string $rawFinalStatus): string
{
    $v = strtolower(trim($rawFinalStatus));
    if ($v === 'completed') return 'completed';
    if ($v === 'withdrawn') return 'withdrawn';
    if ($v === 'needs_qc') return 'needs_qc';
    if ($v === 'in_review') return 'in_review';
    return 'in_review';
}

function normalize_status_filter(string $raw): string
{
    $v = strtolower(trim($raw));
    if ($v === '') return 'completed';
    if ($v === 'all') return 'all';
    if (in_array($v, ['pending', 'in_review', 'needs_qc', 'completed', 'withdrawn'], true)) {
        return $v;
    }
    return 'completed';
}

function curl_json_post(string $url, string $token, array $payload): array
{
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            'X-Integration-Token: ' . $token,
        ],
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_TIMEOUT => 60,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
    ]);

    $resp = curl_exec($ch);
    $errno = curl_errno($ch);
    $err = curl_error($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($errno !== 0) {
        return [
            'ok' => false,
            'http_code' => 0,
            'error' => 'cURL error #' . $errno . ': ' . $err,
            'body' => '',
            'json' => null,
        ];
    }

    $decoded = null;
    if (is_string($resp) && $resp !== '') {
        $decoded = json_decode($resp, true);
    }

    return [
        'ok' => $status >= 200 && $status < 300,
        'http_code' => $status,
        'error' => ($status >= 200 && $status < 300) ? '' : ('HTTP ' . $status),
        'body' => (string)$resp,
        'json' => is_array($decoded) ? $decoded : null,
    ];
}

function get_inputs(): array
{
    $mode = 'single';
    $claimId = '';
    $limit = 50;
    $offset = 0;
    $statusFilter = 'completed';

    if (PHP_SAPI === 'cli') {
        global $argv;
        foreach ((array)$argv as $arg) {
            $arg = (string)$arg;
            if (strpos($arg, '--claim_id=') === 0) {
                $claimId = trim(substr($arg, strlen('--claim_id=')));
            } elseif (strpos($arg, '--mode=') === 0) {
                $mode = strtolower(trim(substr($arg, strlen('--mode='))));
            } elseif (strpos($arg, '--limit=') === 0) {
                $limit = (int)trim(substr($arg, strlen('--limit=')));
            } elseif (strpos($arg, '--offset=') === 0) {
                $offset = (int)trim(substr($arg, strlen('--offset=')));
            } elseif (strpos($arg, '--status=') === 0) {
                $statusFilter = trim(substr($arg, strlen('--status=')));
            }
        }
    } else {
        $claimId = trim((string)($_GET['claim_id'] ?? $_POST['claim_id'] ?? ''));
        $mode = strtolower(trim((string)($_GET['mode'] ?? $_POST['mode'] ?? ($claimId !== '' ? 'single' : 'bulk'))));
        $limit = (int)($_GET['limit'] ?? $_POST['limit'] ?? 50);
        $offset = (int)($_GET['offset'] ?? $_POST['offset'] ?? 0);
        $statusFilter = trim((string)($_GET['status'] ?? $_POST['status'] ?? 'completed'));
    }

    if ($claimId !== '') {
        $mode = 'single';
    } elseif ($mode === '') {
        $mode = 'bulk';
    }

    if ($mode !== 'single' && $mode !== 'bulk') {
        $mode = 'bulk';
    }

    if ($limit < 1) $limit = 1;
    if ($limit > 500) $limit = 500;
    if ($offset < 0) $offset = 0;

    return [
        'mode' => $mode,
        'claim_id' => $claimId,
        'limit' => $limit,
        'offset' => $offset,
        'status_filter' => normalize_status_filter($statusFilter),
    ];
}

function fetch_latest_case_row(PDO $pdo, string $claimId): ?array
{
    $stmt = $pdo->prepare("SELECT
        id, claim_id, claim_date, claim_type, policy_number, policy_type,
        benef_name, benef_age, benef_gender, hospital_name, claim_amount,
        allocation_date, doa_date, dod_date,
        COALESCE(trigger_remarks, '') AS trigger_remarks,
        COALESCE(final_status, 'pending') AS final_status,
        COALESCE(primary_icd_group, '') AS primary_icd_group,
        COALESCE(primary_ailment_code, '') AS primary_ailment_code,
        COALESCE(document_status, '') AS document_status,
        COALESCE(vendor_name, '') AS vendor_name
    FROM excel_case_uploads
    WHERE claim_id = :claim_id
    ORDER BY id DESC
    LIMIT 1");
    $stmt->execute(['claim_id' => $claimId]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function fetch_latest_doctor_row(PDO $pdo, string $claimId): array
{
    $stmt = $pdo->prepare("SELECT
        u.username AS doctor_username,
        a.doctor_user_id,
        a.assigned_at
    FROM case_assignments a
    LEFT JOIN users u ON u.id = a.doctor_user_id
    WHERE a.claim_id = :claim_id
    ORDER BY a.id DESC
    LIMIT 1");
    $stmt->execute(['claim_id' => $claimId]);
    return $stmt->fetch() ?: [];
}

function fetch_latest_analysis_row(PDO $pdo, string $claimId): ?array
{
    $stmt = $pdo->prepare("SELECT
        id,
        model_name,
        admission_required,
        confidence,
        rationale,
        disclaimer,
        raw_response_json,
        report_html,
        created_at,
        doctor_user_id,
        doctor_username
    FROM openai_analysis_results
    WHERE claim_id = :claim_id
    ORDER BY id DESC
    LIMIT 1");
    $stmt->execute(['claim_id' => $claimId]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function build_payload_for_claim(PDO $pdo, string $claimId): array
{
    $case = fetch_latest_case_row($pdo, $claimId);
    if ($case === null) {
        return [
            'ok' => false,
            'error' => 'Claim not found in excel_case_uploads for claim_id=' . $claimId,
        ];
    }

    $doctorRow = fetch_latest_doctor_row($pdo, $claimId);
    $analysis = fetch_latest_analysis_row($pdo, $claimId);

    $doctorUsername = trim((string)($doctorRow['doctor_username'] ?? ''));
    if ($doctorUsername === '') {
        $doctorUsername = trim((string)($analysis['doctor_username'] ?? ''));
    }

    $legacyPayload = $case;
    $legacyPayload['sync_source'] = 'teamrightworks.in/QC';

    $recommendation = infer_recommendation($case, $analysis);
    $statusVal = normalize_claim_status((string)($case['final_status'] ?? ''));

    $reportHtml = '';
    if (is_array($analysis)) {
        $reportHtml = trim((string)($analysis['report_html'] ?? ''));
    }

    $decisionPayload = [
        'source' => 'teamrightworks_sync_script',
        'claim_id' => (string)$case['claim_id'],
        'analysis_id' => is_array($analysis) ? (int)($analysis['id'] ?? 0) : null,
        'legacy_case_row_id' => (int)($case['id'] ?? 0),
        'raw_response_json' => is_array($analysis) ? (string)($analysis['raw_response_json'] ?? '') : '',
    ];

    $payload = [
        'external_claim_id' => (string)$case['claim_id'],
        'patient_name' => (string)($case['benef_name'] ?? ''),
        'patient_identifier' => (string)($case['policy_number'] ?? ''),
        'assigned_doctor_id' => $doctorUsername !== '' ? $doctorUsername : null,
        'status' => $statusVal,
        'priority' => 3,
        'source_channel' => 'teamrightworks.in',
        'tags' => array_values(array_filter([
            (string)($case['claim_type'] ?? ''),
            (string)($case['policy_type'] ?? ''),
            (string)($case['primary_icd_group'] ?? ''),
            (string)($case['hospital_name'] ?? ''),
        ], static function ($v) {
            return trim((string)$v) !== '';
        })),
        'legacy_payload' => $legacyPayload,
        'report_html' => $reportHtml !== '' ? $reportHtml : null,
        'report_status' => $reportHtml !== '' ? 'completed' : 'draft',
        'doctor_username' => $doctorUsername !== '' ? $doctorUsername : null,
        'doctor_opinion' => (string)($case['trigger_remarks'] ?? ''),
        'recommendation' => $recommendation,
        'explanation_summary' => is_array($analysis) ? (string)($analysis['rationale'] ?? '') : '',
        'decision_payload' => $decisionPayload,
        'sync_ref' => 'teamrightworks-' . (string)$case['claim_id'] . '-' . date('YmdHis'),
    ];

    return [
        'ok' => true,
        'claim_id' => (string)$case['claim_id'],
        'payload' => $payload,
        'has_report' => $reportHtml !== '',
        'final_status' => (string)($case['final_status'] ?? 'pending'),
    ];
}

function sync_single_claim(PDO $pdo, string $claimId, string $syncUrl, string $syncToken): array
{
    $built = build_payload_for_claim($pdo, $claimId);
    if (!$built['ok']) {
        return [
            'ok' => false,
            'claim_id' => $claimId,
            'error' => (string)($built['error'] ?? 'Failed to build payload'),
        ];
    }

    $result = curl_json_post($syncUrl, $syncToken, (array)$built['payload']);
    if (!$result['ok']) {
        return [
            'ok' => false,
            'claim_id' => (string)$built['claim_id'],
            'error' => 'Push failed: ' . ($result['error'] ?: 'unknown'),
            'http_code' => $result['http_code'],
            'remote_body' => $result['body'],
        ];
    }

    return [
        'ok' => true,
        'claim_id' => (string)$built['claim_id'],
        'has_report' => (bool)($built['has_report'] ?? false),
        'final_status' => (string)($built['final_status'] ?? ''),
        'remote' => $result['json'] ?? $result['body'],
    ];
}

function fetch_bulk_claim_ids(PDO $pdo, string $statusFilter, int $limit, int $offset): array
{
    $sql = "SELECT e.claim_id AS claim_id FROM (
        SELECT claim_id, MAX(id) AS latest_id
        FROM excel_case_uploads
        WHERE claim_id IS NOT NULL AND claim_id <> ''
        GROUP BY claim_id
    ) latest
    JOIN excel_case_uploads e ON e.claim_id = latest.claim_id AND e.id = latest.latest_id
    WHERE (:status_filter = 'all' OR COALESCE(e.final_status, 'pending') = :status_filter)
    ORDER BY e.id DESC
    LIMIT :limit_val OFFSET :offset_val";

    $stmt = $pdo->prepare($sql);
    $stmt->bindValue(':status_filter', $statusFilter, PDO::PARAM_STR);
    $stmt->bindValue(':limit_val', $limit, PDO::PARAM_INT);
    $stmt->bindValue(':offset_val', $offset, PDO::PARAM_INT);
    $stmt->execute();

    $rows = $stmt->fetchAll();
    $ids = [];
    foreach ($rows as $row) {
        $id = trim((string)($row['claim_id'] ?? ''));
        if ($id !== '') $ids[] = $id;
    }
    return $ids;
}

$syncUrl = env_or_default('VERIFAI_SYNC_URL', 'https://verifai.in/api/v1/integrations/teamrightworks/case-intake');
$syncToken = env_or_default('VERIFAI_SYNC_TOKEN', '');
$webSecret = env_or_default('VERIFAI_SYNC_WEB_SECRET', '');

if ($syncToken === '') {
    out_json(500, [
        'ok' => false,
        'error' => 'VERIFAI_SYNC_TOKEN is not configured in .env',
    ]);
}

if (PHP_SAPI !== 'cli') {
    if ($webSecret === '') {
        out_json(403, [
            'ok' => false,
            'error' => 'Web execution disabled. Set VERIFAI_SYNC_WEB_SECRET to enable.',
        ]);
    }
    $provided = trim((string)($_GET['key'] ?? $_POST['key'] ?? ''));
    if ($provided === '' || !hash_equals($webSecret, $provided)) {
        out_json(401, [
            'ok' => false,
            'error' => 'Invalid sync key.',
        ]);
    }
}

$input = get_inputs();

try {
    $pdo = pdo_db();

    if ($input['mode'] === 'single') {
        $claimId = (string)$input['claim_id'];
        if ($claimId === '') {
            out_json(400, [
                'ok' => false,
                'error' => 'Missing claim_id for single mode.',
            ]);
        }

        $single = sync_single_claim($pdo, $claimId, $syncUrl, $syncToken);
        if (!$single['ok']) {
            out_json(502, $single);
        }

        out_json(200, [
            'ok' => true,
            'mode' => 'single',
            'claim_id' => $claimId,
            'sync_url' => $syncUrl,
            'result' => $single,
        ]);
    }

    $claimIds = fetch_bulk_claim_ids(
        $pdo,
        (string)$input['status_filter'],
        (int)$input['limit'],
        (int)$input['offset']
    );

    $success = 0;
    $failed = 0;
    $details = [];

    foreach ($claimIds as $cid) {
        $res = sync_single_claim($pdo, $cid, $syncUrl, $syncToken);
        if ($res['ok']) {
            $success++;
        } else {
            $failed++;
        }
        $details[] = $res;
    }

    out_json(200, [
        'ok' => true,
        'mode' => 'bulk',
        'sync_url' => $syncUrl,
        'status_filter' => (string)$input['status_filter'],
        'limit' => (int)$input['limit'],
        'offset' => (int)$input['offset'],
        'total_selected' => count($claimIds),
        'success' => $success,
        'failed' => $failed,
        'results' => $details,
    ]);
} catch (Throwable $e) {
    out_json(500, [
        'ok' => false,
        'error' => $e->getMessage(),
    ]);
}



POST['status'] ?? 'completed'));
    }

    if ($claimId !== '') {
        $mode = 'single';
    } elseif ($mode === '') {
        $mode = 'bulk';
    }

    if ($mode !== 'single' && $mode !== 'bulk' && $mode !== 'users') {
        $mode = 'bulk';
    }

    if ($limit < 1) $limit = 1;
    if ($limit > 500) $limit = 500;
    if ($offset < 0) $offset = 0;

    return [
        'mode' => $mode,
        'claim_id' => $claimId,
        'limit' => $limit,
        'offset' => $offset,
        'status_filter' => normalize_status_filter($statusFilter),
    ];
}

function fetch_latest_case_row(PDO $pdo, string $claimId): ?array
{
    $stmt = $pdo->prepare("SELECT
        id, claim_id, claim_date, claim_type, policy_number, policy_type,
        benef_name, benef_age, benef_gender, hospital_name, claim_amount,
        allocation_date, doa_date, dod_date,
        COALESCE(trigger_remarks, '') AS trigger_remarks,
        COALESCE(final_status, 'pending') AS final_status,
        COALESCE(primary_icd_group, '') AS primary_icd_group,
        COALESCE(primary_ailment_code, '') AS primary_ailment_code,
        COALESCE(document_status, '') AS document_status,
        COALESCE(vendor_name, '') AS vendor_name
    FROM excel_case_uploads
    WHERE claim_id = :claim_id
    ORDER BY id DESC
    LIMIT 1");
    $stmt->execute(['claim_id' => $claimId]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function fetch_latest_doctor_row(PDO $pdo, string $claimId): array
{
    $stmt = $pdo->prepare("SELECT
        u.username AS doctor_username,
        a.doctor_user_id,
        a.assigned_at
    FROM case_assignments a
    LEFT JOIN users u ON u.id = a.doctor_user_id
    WHERE a.claim_id = :claim_id
    ORDER BY a.id DESC
    LIMIT 1");
    $stmt->execute(['claim_id' => $claimId]);
    return $stmt->fetch() ?: [];
}

function fetch_latest_analysis_row(PDO $pdo, string $claimId): ?array
{
    $stmt = $pdo->prepare("SELECT
        id,
        model_name,
        admission_required,
        confidence,
        rationale,
        disclaimer,
        raw_response_json,
        report_html,
        created_at,
        doctor_user_id,
        doctor_username
    FROM openai_analysis_results
    WHERE claim_id = :claim_id
    ORDER BY id DESC
    LIMIT 1");
    $stmt->execute(['claim_id' => $claimId]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function build_payload_for_claim(PDO $pdo, string $claimId): array
{
    $case = fetch_latest_case_row($pdo, $claimId);
    if ($case === null) {
        return [
            'ok' => false,
            'error' => 'Claim not found in excel_case_uploads for claim_id=' . $claimId,
        ];
    }

    $doctorRow = fetch_latest_doctor_row($pdo, $claimId);
    $analysis = fetch_latest_analysis_row($pdo, $claimId);

    $doctorUsername = trim((string)($doctorRow['doctor_username'] ?? ''));
    if ($doctorUsername === '') {
        $doctorUsername = trim((string)($analysis['doctor_username'] ?? ''));
    }

    $legacyPayload = $case;
    $legacyPayload['sync_source'] = 'teamrightworks.in/QC';

    $recommendation = infer_recommendation($case, $analysis);
    $statusVal = normalize_claim_status((string)($case['final_status'] ?? ''));

    $reportHtml = '';
    if (is_array($analysis)) {
        $reportHtml = trim((string)($analysis['report_html'] ?? ''));
    }

    $decisionPayload = [
        'source' => 'teamrightworks_sync_script',
        'claim_id' => (string)$case['claim_id'],
        'analysis_id' => is_array($analysis) ? (int)($analysis['id'] ?? 0) : null,
        'legacy_case_row_id' => (int)($case['id'] ?? 0),
        'raw_response_json' => is_array($analysis) ? (string)($analysis['raw_response_json'] ?? '') : '',
    ];

    $payload = [
        'external_claim_id' => (string)$case['claim_id'],
        'patient_name' => (string)($case['benef_name'] ?? ''),
        'patient_identifier' => (string)($case['policy_number'] ?? ''),
        'assigned_doctor_id' => $doctorUsername !== '' ? $doctorUsername : null,
        'status' => $statusVal,
        'priority' => 3,
        'source_channel' => 'teamrightworks.in',
        'tags' => array_values(array_filter([
            (string)($case['claim_type'] ?? ''),
            (string)($case['policy_type'] ?? ''),
            (string)($case['primary_icd_group'] ?? ''),
            (string)($case['hospital_name'] ?? ''),
        ], static function ($v) {
            return trim((string)$v) !== '';
        })),
        'legacy_payload' => $legacyPayload,
        'report_html' => $reportHtml !== '' ? $reportHtml : null,
        'report_status' => $reportHtml !== '' ? 'completed' : 'draft',
        'doctor_username' => $doctorUsername !== '' ? $doctorUsername : null,
        'doctor_opinion' => (string)($case['trigger_remarks'] ?? ''),
        'recommendation' => $recommendation,
        'explanation_summary' => is_array($analysis) ? (string)($analysis['rationale'] ?? '') : '',
        'decision_payload' => $decisionPayload,
        'sync_ref' => 'teamrightworks-' . (string)$case['claim_id'] . '-' . date('YmdHis'),
    ];

    return [
        'ok' => true,
        'claim_id' => (string)$case['claim_id'],
        'payload' => $payload,
        'has_report' => $reportHtml !== '',
        'final_status' => (string)($case['final_status'] ?? 'pending'),
    ];
}

function sync_single_claim(PDO $pdo, string $claimId, string $syncUrl, string $syncToken): array
{
    $built = build_payload_for_claim($pdo, $claimId);
    if (!$built['ok']) {
        return [
            'ok' => false,
            'claim_id' => $claimId,
            'error' => (string)($built['error'] ?? 'Failed to build payload'),
        ];
    }

    $result = curl_json_post($syncUrl, $syncToken, (array)$built['payload']);
    if (!$result['ok']) {
        return [
            'ok' => false,
            'claim_id' => (string)$built['claim_id'],
            'error' => 'Push failed: ' . ($result['error'] ?: 'unknown'),
            'http_code' => $result['http_code'],
            'remote_body' => $result['body'],
        ];
    }

    return [
        'ok' => true,
        'claim_id' => (string)$built['claim_id'],
        'has_report' => (bool)($built['has_report'] ?? false),
        'final_status' => (string)($built['final_status'] ?? ''),
        'remote' => $result['json'] ?? $result['body'],
    ];
}

function fetch_bulk_claim_ids(PDO $pdo, string $statusFilter, int $limit, int $offset): array
{
    $sql = "SELECT e.claim_id AS claim_id FROM (
        SELECT claim_id, MAX(id) AS latest_id
        FROM excel_case_uploads
        WHERE claim_id IS NOT NULL AND claim_id <> ''
        GROUP BY claim_id
    ) latest
    JOIN excel_case_uploads e ON e.claim_id = latest.claim_id AND e.id = latest.latest_id
    WHERE (:status_filter = 'all' OR COALESCE(e.final_status, 'pending') = :status_filter)
    ORDER BY e.id DESC
    LIMIT :limit_val OFFSET :offset_val";

    $stmt = $pdo->prepare($sql);
    $stmt->bindValue(':status_filter', $statusFilter, PDO::PARAM_STR);
    $stmt->bindValue(':limit_val', $limit, PDO::PARAM_INT);
    $stmt->bindValue(':offset_val', $offset, PDO::PARAM_INT);
    $stmt->execute();

    $rows = $stmt->fetchAll();
    $ids = [];
    foreach ($rows as $row) {
        $id = trim((string)($row['claim_id'] ?? ''));
        if ($id !== '') $ids[] = $id;
    }
    return $ids;
}

$syncUrl = env_or_default('VERIFAI_SYNC_URL', 'https://verifai.in/api/v1/integrations/teamrightworks/case-intake');
$syncToken = env_or_default('VERIFAI_SYNC_TOKEN', '');
$webSecret = env_or_default('VERIFAI_SYNC_WEB_SECRET', '');

if ($syncToken === '') {
    out_json(500, [
        'ok' => false,
        'error' => 'VERIFAI_SYNC_TOKEN is not configured in .env',
    ]);
}

if (PHP_SAPI !== 'cli') {
    if ($webSecret === '') {
        out_json(403, [
            'ok' => false,
            'error' => 'Web execution disabled. Set VERIFAI_SYNC_WEB_SECRET to enable.',
        ]);
    }
    $provided = trim((string)($_GET['key'] ?? $_POST['key'] ?? ''));
    if ($provided === '' || !hash_equals($webSecret, $provided)) {
        out_json(401, [
            'ok' => false,
            'error' => 'Invalid sync key.',
        ]);
    }
}

$input = get_inputs();

try {
    $pdo = pdo_db();

    if ($input['mode'] === 'single') {
        $claimId = (string)$input['claim_id'];
        if ($claimId === '') {
            out_json(400, [
                'ok' => false,
                'error' => 'Missing claim_id for single mode.',
            ]);
        }

        $single = sync_single_claim($pdo, $claimId, $syncUrl, $syncToken);
        if (!$single['ok']) {
            out_json(502, $single);
        }

        out_json(200, [
            'ok' => true,
            'mode' => 'single',
            'claim_id' => $claimId,
            'sync_url' => $syncUrl,
            'result' => $single,
        ]);
    }

    $claimIds = fetch_bulk_claim_ids(
        $pdo,
        (string)$input['status_filter'],
        (int)$input['limit'],
        (int)$input['offset']
    );

    $success = 0;
    $failed = 0;
    $details = [];

    foreach ($claimIds as $cid) {
        $res = sync_single_claim($pdo, $cid, $syncUrl, $syncToken);
        if ($res['ok']) {
            $success++;
        } else {
            $failed++;
        }
        $details[] = $res;
    }

    out_json(200, [
        'ok' => true,
        'mode' => 'bulk',
        'sync_url' => $syncUrl,
        'status_filter' => (string)$input['status_filter'],
        'limit' => (int)$input['limit'],
        'offset' => (int)$input['offset'],
        'total_selected' => count($claimIds),
        'success' => $success,
        'failed' => $failed,
        'results' => $details,
    ]);
} catch (Throwable $e) {
    out_json(500, [
        'ok' => false,
        'error' => $e->getMessage(),
    ]);
}





