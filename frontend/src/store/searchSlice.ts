import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import { searchEnterprises, SearchResult } from "../api";

export const fetchSearch = createAsyncThunk(
  "search/fetch",
  async (q: string) => searchEnterprises(q),
);

interface SearchState {
  query: string;
  results: SearchResult[];
  loading: boolean;
  error: string | null;
}

const initialState: SearchState = {
  query: "",
  results: [],
  loading: false,
  error: null,
};

const searchSlice = createSlice({
  name: "search",
  initialState,
  reducers: {
    setQuery(state, action) {
      state.query = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSearch.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSearch.fulfilled, (state, action) => {
        state.loading = false;
        state.results = action.payload;
      })
      .addCase(fetchSearch.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || "Erreur";
      });
  },
});

export const { setQuery } = searchSlice.actions;
export default searchSlice.reducer;
