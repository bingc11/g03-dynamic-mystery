// Keep the upstream Create React App entry point; set local defaults on Windows and Unix.
process.env.HOST = "127.0.0.1";
process.env.PORT = process.env.PORT || "5001";
process.env.BROWSER = "none";
process.env.REACT_APP_API_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:10000";
require("react-scripts/scripts/start");
