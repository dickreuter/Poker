import axios from "axios";
import { useEffect, useState } from "react";

export const API_URL =
  import.meta.env.VITE_REACT_APP_API_URL || "https://dickreuter.com:7778";

export const useDlLink = () => {
  const [dlLink, setDlLink] = useState("");

  useEffect(() => {
    const fetchDlLink = async () => {
      try {
        const response = await axios.post(`${API_URL}/get_internal`);
        setDlLink(response.data[0].dl);
      } catch (error) {
        console.error("Error fetching dl link:", error);
      }
    };

    fetchDlLink();
  }, []);

  return dlLink;
};
