import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
    throw new Error("The React root element was not found.");
}

ReactDOM.createRoot(rootElement).render(<App />);