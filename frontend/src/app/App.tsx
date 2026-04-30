import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { HomePage } from "@/features/home/HomePage";
import { ReviewNewPage } from "@/features/review/ReviewNewPage";
import { ResultsPage } from "@/features/review/ResultsPage";
import { NotFoundPage } from "@/features/home/NotFoundPage";
import { BatchUploadPage } from "@/features/batch/BatchUploadPage";
import { QueuePage } from "@/features/queue/QueuePage";
import { ApplicationDetailPage } from "@/features/queue/ApplicationDetailPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/review/new" element={<ReviewNewPage />} />
        <Route path="/review/:id" element={<ResultsPage />} />
        <Route path="/batches/new" element={<BatchUploadPage />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route
          path="/queue/applications/:id"
          element={<ApplicationDetailPage />}
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}
