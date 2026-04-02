<?php
declare(strict_types=1);

require_once __DIR__ . '/config/db.php';

header('Content-Type: application/json; charset=utf-8');

function out(int $status, array $payload): void
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

$key = trim((string)($_GET['key'] ?? ''));
if ($key !== 'sync_dL1EuYoMu1wbtoZP7WisGdC3eKqbLHT5') {
    out(401, ['ok' => false, 'error' => 'invalid key']);
}

try {
    $pdo = pdo_db();
    $colsStmt = $pdo->query("SHOW COLUMNS FROM excel_case_uploads");
    $cols = $colsStmt ? $colsStmt->fetchAll(PDO::FETCH_COLUMN, 0) : [];
    $colSet = [];
    foreach ($cols as $c) {
        $colSet[strtolower((string)$c)] = true;
    }

    $targets = ['tagging', 'subtagging', 'opinion', 'trigger_remarks', 'doctor_opinion', 'qc_status', 'report_export_status'];
    $counts = [];
    $samples = [];

    foreach ($targets as $col) {
        if (!isset($colSet[$col])) {
            $counts[$col] = null;
            $samples[$col] = null;
            continue;
        }
        $qCount = "SELECT COUNT(*) FROM excel_case_uploads WHERE COALESCE(TRIM(CAST($col AS CHAR)), '') <> ''";
        $counts[$col] = (int)$pdo->query($qCount)->fetchColumn();

        $qSample = "SELECT claim_id, CAST($col AS CHAR) AS val FROM excel_case_uploads WHERE COALESCE(TRIM(CAST($col AS CHAR)), '') <> '' ORDER BY id DESC LIMIT 3";
        $rows = $pdo->query($qSample)->fetchAll(PDO::FETCH_ASSOC);
        $samples[$col] = $rows ?: [];
    }

    out(200, [
        'ok' => true,
        'columns' => $cols,
        'counts' => $counts,
        'samples' => $samples,
    ]);
} catch (Throwable $e) {
    out(500, ['ok' => false, 'error' => $e->getMessage()]);
}

