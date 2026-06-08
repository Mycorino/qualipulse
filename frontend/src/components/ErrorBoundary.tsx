import { Component, ErrorInfo, ReactNode } from "react";
import i18n from "../i18n";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="error-boundary-fallback">
          <div className="error-boundary-icon">⚠️</div>
          <h2 className="error-boundary-title">{i18n.t("shell:errorBoundary.title")}</h2>
          <p className="error-boundary-text">
            {i18n.t("shell:errorBoundary.text")}
          </p>
          <button
            className="btn btn-primary"
            onClick={() => window.location.reload()}
          >
            {i18n.t("shell:errorBoundary.refresh")}
          </button>
          {import.meta.env.DEV && this.state.error && (
            <pre className="error-boundary-detail">
              {this.state.error.message}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
