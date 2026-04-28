import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { HomePage } from "@/features/home/HomePage";
import { ReviewNewPage } from "@/features/review/ReviewNewPage";
import { ResultsPage } from "@/features/review/ResultsPage";
import { NotFoundPage } from "@/features/home/NotFoundPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/review/new" element={<ReviewNewPage />} />
        <Route path="/review/:id" element={<ResultsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}
