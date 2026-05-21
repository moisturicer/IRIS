import { RouterProvider } from "react-router-dom";
import { router } from "@/router";
import { ToastContainer } from "@/components/ui/Toast";

export default function App() {
  return (
    <>
      <RouterProvider router={router} />
      {/* Global toast notifications -- rendered outside the router so they survive page transitions */}
      <ToastContainer />
    </>
  );
}
