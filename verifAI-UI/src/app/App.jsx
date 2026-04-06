import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { RequireAuth } from "./routes";
import Login from "../components/pages/Login";
import WorkspaceLayout from "./WorkspaceLayout";
import Dashboard from "../components/pages/Dashboard";
import Placeholder from "../components/pages/Placeholder";
import { useParams } from "react-router-dom";
import ChangePassword from "../components/pages/ChangePassword";
import ResetUserPassword from "../components/pages/ResetUserPassword";
import CreateUser from "../components/pages/CreateUser";
import AssignedCases from "../components/pages/AssignedCases";
import UploadExcel from "../components/pages/UploadExcel";
import AssignCases from "../components/pages/AssignCases";
import WithdrawnClaims from "../components/pages/WithdrawnClaims";
import UploadDocument from "../components/pages/UploadDocument";
import CompletedReports from "../components/pages/CompletedReports";
import ExportData from "../components/pages/ExportData";
import AllotmentDateWise from "../components/pages/AllotmentDateWise";
import StorageMaintenance from "../components/pages/StorageMaintenance";
import ClaimRules from "../components/pages/ClaimRules";
import DiagnosisCriteria from "../components/pages/DiagnosisCriteria";
import PaymentSheet from "../components/pages/PaymentSheet";
import BankDetails from "../components/pages/BankDetails";
import Medicines from "../components/pages/Medicines";
import RuleSuggestions from "../components/pages/RuleSuggestions";
import LegacySync from "../components/pages/LegacySync";
import AIPrompt from "../components/pages/AIPrompt";
import AuditClaims from "../components/pages/AuditClaims";
import CaseDetail from "../components/pages/CaseDetail";
import Monitor from "../components/pages/Monitor";
import ReportEditor from "../components/pages/ReportEditor";
import AuditorQC from "../components/pages/AuditorQC";

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
