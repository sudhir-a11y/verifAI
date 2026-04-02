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

function normalize_role(string $raw): string
{
    $v = strtolower(trim($raw));
    if ($v === 'super_admin' || $v === 'superadmin' || $v === 'admin') return 'super_admin';
    if ($v === 'doctor' || $v === 'dr' || $v === 'physician') return 'doctor';
    if ($v === 'auditor' || $v === 'audit' || $v === 'qa') return 'auditor';
    return 'user';
}

$key = trim((string)($_GET['key'] ?? ''));
if ($key !== 'sync_dL1EuYoMu1wbtoZP7WisGdC3eKqbLHT5') {
    out(401, ['ok' => false, 'error' => 'invalid key']);
}

try {
    $pdo = pdo_db();

    $colStmt = $pdo->query("SHOW COLUMNS FROM users");
    $cols = $colStmt ? $colStmt->fetchAll(PDO::FETCH_COLUMN, 0) : [];
    $colSet = [];
    foreach ($cols as $c) {
        $colSet[strtolower((string)$c)] = true;
    }

    $roleCol = isset($colSet['role']) ? 'role' : (isset($colSet['user_role']) ? 'user_role' : '');
    $activeCol = isset($colSet['is_active']) ? 'is_active' : (isset($colSet['status']) ? 'status' : '');
    if ($roleCol === '') {
        out(500, ['ok' => false, 'error' => 'users.role column not found', 'columns' => $cols]);
    }

    $where = "WHERE COALESCE(TRIM(username), '') <> ''";
    if ($activeCol === 'is_active') {
        $where .= " AND COALESCE(is_active, 1) = 1";
    } elseif ($activeCol === 'status') {
        $where .= " AND LOWER(COALESCE(TRIM(status), 'active')) IN ('1','active','enabled')";
    }

    $sql = "SELECT id, username, $roleCol AS role_raw FROM users $where ORDER BY id ASC";
    $rows = $pdo->query($sql)->fetchAll(PDO::FETCH_ASSOC);

    $items = [];
    foreach ($rows as $r) {
        $username = trim((string)($r['username'] ?? ''));
        if ($username === '') continue;
        $roleRaw = trim((string)($r['role_raw'] ?? ''));
        $items[] = [
            'id' => (int)($r['id'] ?? 0),
            'username' => $username,
            'role_raw' => $roleRaw,
            'role_normalized' => normalize_role($roleRaw),
        ];
    }

    out(200, [
        'ok' => true,
        'count' => count($items),
        'columns' => $cols,
        'items' => $items,
    ]);
} catch (Throwable $e) {
    out(500, ['ok' => false, 'error' => $e->getMessage()]);
}

