import { Component } from "react";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[JENIX] Page error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display:"flex", flexDirection:"column",
          alignItems:"center", justifyContent:"center",
          height:"60vh", textAlign:"center", padding:"40px"
        }}>
          <div style={{ fontSize:"48px", marginBottom:"16px" }}>⚠️</div>
          <div style={{ color:"#e0e0e0", fontSize:"20px",
                        fontWeight:700, marginBottom:"8px" }}>
            Something went wrong
          </div>
          <div style={{ color:"#666", fontSize:"13px",
                        marginBottom:"24px", maxWidth:"400px" }}>
            {this.state.error?.message || "An unexpected error occurred"}
          </div>
          <button
            onClick={() => {
              this.setState({ hasError:false, error:null });
              window.location.href = "/";
            }}
            style={{
              padding:"10px 24px", background:"#00bcd4",
              color:"#000", border:"none", borderRadius:"8px",
              fontWeight:700, fontSize:"13px", cursor:"pointer"
            }}>
            Return to Dashboard
          </button>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding:"10px 24px", background:"transparent",
              color:"#666", border:"1px solid #2a2a3e",
              borderRadius:"8px", fontWeight:600,
              fontSize:"13px", cursor:"pointer",
              marginTop:"8px"
            }}>
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
