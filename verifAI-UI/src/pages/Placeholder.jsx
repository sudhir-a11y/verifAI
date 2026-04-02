import { PAGE_TITLES } from "../app/nav";

export default function Placeholder({ page }) {
  return (
    <div className="space-y-2 text-sm text-slate-700">
      <p>
        <span className="font-medium">{PAGE_TITLES[page] || page}</span> is not migrated yet.
      </p>
      <p className="text-slate-600">
        Next step: port the corresponding logic from `backend/app/web/qc/public/workspace.js` into React components +
        `src/services/`.
      </p>
    </div>
  );
}

