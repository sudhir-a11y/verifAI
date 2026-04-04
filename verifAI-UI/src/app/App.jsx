import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { RequireAuth } from "./routes";
import Login from "../pages/Login";
import WorkspaceLayout from "./WorkspaceLayout";
import Dashboard from "../pages/Dashboard";
import Placeholder from "../pages/Placeholder";
import { useParams } from "react-router-dom";
import ChangePassword from "../pages/ChangePassword";
import ResetUserPassword from "../pages/ResetUserPassword";
import CreateUser from "../pages/CreateUser";
import AssignedCases from "../pages/AssignedCases";
import UploadExcel from "../pages/UploadExcel";
import AssignCases from "../pages/AssignCases";
import WithdrawnClaims from "../pages/WithdrawnClaims";
import UploadDocument from "../pages/UploadDocument";
import CompletedReports from "../pages/CompletedReports";
import ExportData from "../pages/ExportData";
import AllotmentDateWise from "../pages/AllotmentDateWise";
import StorageMaintenance from "../pages/StorageMaintenance";
import ClaimRules from "../pages/ClaimRules";
import DiagnosisCriteria from "../pages/DiagnosisCriteria";
import PaymentSheet from "../pages/PaymentSheet";
import BankDetails from "../pages/BankDetails";
import Medicines from "../pages/Medicines";
import RuleSuggestions from "../pages/RuleSuggestions";
import LegacySync from "../pages/LegacySync";
import AIPrompt from "../pages/AIPrompt";
import AuditClaims from "../pages/AuditClaims";
import CaseDetail from "../pages/CaseDetail";
import Monitor from "../pages/Monitor";
import ReportEditor from "../pages/ReportEditor";
import AuditorQC from "../pages/AuditorQC";

function LegacyQcRedirect() {
  const { page } = useParams();
  const location = useLocation();
  const p = String(page || "dashboard");
  return <Navigate to={`/app/${p}${location.search || ""}`} replace />;
}

function WorkspacePage() {
  const { page } = useParams();
  const p = String(page || "dashboard");
  if (p === "dashboard") return <Dashboard />;
  if (p === "create-user") return <CreateUser />;
  if (p === "change-password") return <ChangePassword />;
  if (p === "reset-user-password") return <ResetUserPassword />;
  if (p === "assigned-cases") return <AssignedCases />;
  if (p === "upload-excel") return <UploadExcel />;
  if (p === "assign-cases") return <AssignCases />;
  if (p === "withdrawn-claims") return <WithdrawnClaims />;
  if (p === "upload-document") return <UploadDocument />;
  if (p === "completed-not-uploaded") return <CompletedReports defaultStatus="pending" />;
  if (p === "completed-uploaded") return <CompletedReports defaultStatus="uploaded" />;
  if (p === "export-data") return <ExportData />;
  if (p === "allotment-date-wise") return <AllotmentDateWise />;
  if (p === "storage-maintenance") return <StorageMaintenance />;
  if (p === "claim-rules") return <ClaimRules />;
  if (p === "diagnosis-criteria") return <DiagnosisCriteria />;
  if (p === "payment-sheet") return <PaymentSheet />;
  if (p === "bank-details") return <BankDetails />;
  if (p === "medicines") return <Medicines />;
  if (p === "rule-suggestions") return <RuleSuggestions />;
  if (p === "legacy-sync") return <LegacySync />;
  if (p === "ai-prompt") return <AIPrompt />;
  if (p === "audit-claims") return <AuditClaims />;
  if (p === "case-detail") return <CaseDetail />;
  return <Placeholder page={p} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/qc/login" element={<Navigate to="/login" replace />} />
      <Route element={<RequireAuth />}>
        <Route path="/qc/:role/:page" element={<LegacyQcRedirect />} />
      </Route>
      <Route path="/login" element={<Login />} />
      <Route path="/monitor" element={<Monitor />} />
      <Route element={<RequireAuth />}>
        <Route path="/report-editor" element={<ReportEditor />} />
        <Route path="/auditor-qc" element={<AuditorQC />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
        <Route path="/app" element={<Navigate to="/app/dashboard" replace />} />
        <Route path="/app/:page" element={<WorkspaceLayout />}>
          <Route index element={<WorkspacePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
