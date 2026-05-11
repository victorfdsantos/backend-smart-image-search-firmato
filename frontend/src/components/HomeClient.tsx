"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Topbar } from "@/components/Topbar";
import { SearchPanel } from "@/components/SearchPanel";
import { ProductGrid } from "@/components/ProductGrid";
import { Pagination } from "@/components/Pagination";
import { PreviewPanel } from "@/components/PreviewPanel";
import { ImportModal } from "@/components/ImportModal";
import {
  getProducts,
  getProductDetail,
  searchProducts,
  thumbnailUrl,
  imageUrl,
} from "@/lib/api";
import { parseFiltersFromUrl, buildSearchUrl } from "@/lib/utils";
import { useDebounce } from "@/hooks/useDebounce";
import type { ProductSummary, ProductDetail, FilterMap } from "@/types";

const PAGE_SIZE = 12;

export function HomeClient() {
  // ----------------------------------------------------------------- state
  const [importOpen, setImportOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);

  const [searchText, setSearchText] = useState("");
  const [uploadedImage, setUploadedImage] = useState("");
  const imageFileRef = useRef<File | null>(null);
  const [filters, setFilters] = useState<FilterMap>({});

  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSearching, setIsSearching] = useState(false);

  // preview usa imagem de OUTPUT (alta qualidade)
  const [selectedImage, setSelectedImage] = useState("");
  const [selectedProduct, setSelectedProduct] = useState<ProductDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [similarProducts, setSimilarProducts] = useState<ProductSummary[]>([]);

  const isInSearch = !!(searchText.trim() || imageFileRef.current);
  const debouncedSearch = useDebounce(searchText, 500);

  // ------------------------------------------------------------ URL sync
  const pushUrl = useCallback(
    (opts: { q?: string; page?: number; img?: string; filters?: FilterMap }) => {
      window.history.replaceState(null, "", buildSearchUrl(opts));
    },
    []
  );

  // --------------------------------------------------------- load gallery
  const loadGallery = useCallback(
    async (p = page, f = filters) => {
      setIsLoading(true);
      try {
        const data = await getProducts(p, PAGE_SIZE, f);
        setProducts(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
      } finally {
        setIsLoading(false);
      }
    },
    [page, filters]
  );

  // ------------------------------------------------------------ run search
  const runSearch = useCallback(
    async (q: string, f = filters) => {
      setIsSearching(true);
      try {
        const data = await searchProducts(q || undefined, imageFileRef.current, 12, f);

        const enriched = await Promise.all(
          data.items.map(async (item) => {
            const detail = await getProductDetail(item.id_produto);
            return {
              id_produto:          item.id_produto,
              imagem_url:          thumbnailUrl(item.id_produto),
              nome_produto:        detail?.nome_produto        ?? "",
              marca:               detail?.marca               ?? "",
              categoria_principal: detail?.categoria_principal ?? "",
              faixa_preco:         detail?.faixa_preco         ?? "",
              altura_cm:           detail?.altura_cm,
              largura_cm:          detail?.largura_cm,
              profundidade_cm:     detail?.profundidade_cm,
            } satisfies ProductSummary;
          })
        );

        setProducts(enriched);
        setTotal(data.total);
        setTotalPages(1);
      } finally {
        setIsSearching(false);
      }
    },
    [filters]
  );

  // ------------------------------------------------------- similar products
  const loadSimilar = useCallback(
    async (productId: string | number, outputImgUrl: string) => {
      setSimilarProducts([]);
      try {
        const imgRes = await fetch(outputImgUrl, { mode: "cors" });
        const blob = await imgRes.blob();
        const file = new File([blob], "query.jpg", { type: "image/jpeg" });

        const data = await searchProducts(undefined, file, 10);

        const enriched = await Promise.all(
          data.items
            .filter((item) => String(item.id_produto) !== String(productId))
            .slice(0, 6)
            .map(async (item) => {
              const detail = await getProductDetail(item.id_produto);
              return {
                id_produto:          item.id_produto,
                imagem_url:          thumbnailUrl(item.id_produto),
                nome_produto:        detail?.nome_produto        ?? "",
                marca:               detail?.marca               ?? "",
                categoria_principal: detail?.categoria_principal ?? "",
                faixa_preco:         detail?.faixa_preco         ?? "",
                altura_cm:           detail?.altura_cm,
                largura_cm:          detail?.largura_cm,
                profundidade_cm:     detail?.profundidade_cm,
              } satisfies ProductSummary;
            })
        );

        setSimilarProducts(enriched);
      } catch {
        setSimilarProducts([]);
      }
    },
    []
  );

  // ---------------------------------------------------------- load detail
  const loadDetail = useCallback(async (id: string | number) => {
    setLoadingDetail(true);
    try {
      const detail = await getProductDetail(id);
      setSelectedProduct(detail);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  // ---------------------------------------------------- select a product
  const openProduct = useCallback(
    (productId: string | number) => {
      const outputUrl = imageUrl(productId);
      setSelectedImage(outputUrl);
      setSelectedProduct(null);
      setSimilarProducts([]);
      loadDetail(productId);
      loadSimilar(productId, outputUrl);
      return outputUrl;
    },
    [loadDetail, loadSimilar]
  );

  // --------------------------------------------------------- on mount: URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q  = params.get("q")    ?? "";
    const p  = parseInt(params.get("page") ?? "1", 10);
    const img = params.get("img") ?? "";
    const f  = parseFiltersFromUrl(window.location.search);

    setSearchText(q);
    setPage(Math.max(1, p));
    setFilters(f);

    if (q || Object.keys(f).length > 0) {
      runSearch(q, f);
    } else {
      loadGallery(p, f);
    }

    if (img) {
      const match = img.match(/\/(\d+)\.jpg$/);
      if (match) {
        const pid = match[1];
        setSelectedImage(imageUrl(pid));
        loadDetail(pid);
        loadSimilar(pid, imageUrl(pid));
      } else {
        setSelectedImage(img);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ----------------------------------------------- debounced text search
  useEffect(() => {
    if (!debouncedSearch.trim() && !imageFileRef.current) {
      loadGallery(1, filters);
      setPage(1);
      pushUrl({ filters });
      return;
    }
    runSearch(debouncedSearch, filters);
    pushUrl({ q: debouncedSearch, filters });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  // ------------------------------------------------------------- handlers

  const handleSearchChange = (text: string) => {
    setSearchText(text);
    setPage(1);
    setSelectedImage("");
    setSelectedProduct(null);
    setSimilarProducts([]);
  };

  const handleSearchCommit = (text: string) => {
    setSearchText(text);
    runSearch(text, filters);
    pushUrl({ q: text, filters });
  };

  const handleImageUpload = (file: File) => {
    imageFileRef.current = file;
    const reader = new FileReader();
    reader.onload = (e) => setUploadedImage(e.target?.result as string);
    reader.readAsDataURL(file);
    setPage(1);
    runSearch(searchText, filters);
    pushUrl({ q: searchText, filters });
  };

  const handleImageClear = () => {
    imageFileRef.current = null;
    setUploadedImage("");
    if (searchText.trim()) {
      runSearch(searchText, filters);
    } else {
      loadGallery(1, filters);
    }
    pushUrl({ q: searchText, filters });
  };

  const handleFilterToggle = (field: string, value: string) => {
    setFilters((prev) => {
      const current = prev[field] ?? [];
      const next    = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      const updated = next.length
        ? { ...prev, [field]: next }
        : Object.fromEntries(Object.entries(prev).filter(([k]) => k !== field));
      setPage(1);
      if (isInSearch) runSearch(searchText, updated);
      else            loadGallery(1, updated);
      pushUrl({ q: searchText, filters: updated });
      return updated;
    });
  };

  const handleFilterRemove   = (field: string, value: string) => handleFilterToggle(field, value);

  const handleFilterClearAll = () => {
    setFilters({});
    setPage(1);
    if (isInSearch) runSearch(searchText, {});
    else            loadGallery(1, {});
    pushUrl({ q: searchText });
  };

  const handleClearAll = () => {
    imageFileRef.current = null;
    setUploadedImage("");
    setSearchText("");
    setFilters({});
    setPage(1);
    setSelectedImage("");
    setSelectedProduct(null);
    setSimilarProducts([]);
    loadGallery(1, {});
    pushUrl({});
  };

  const handleSelectProduct = (product: ProductSummary) => {
    const outputUrl = openProduct(product.id_produto);
    pushUrl({ q: searchText, page, img: outputUrl, filters });
  };

  const handleSelectSimilar = (product: ProductSummary) => {
    const outputUrl = openProduct(product.id_produto);
    pushUrl({ q: searchText, page, img: outputUrl, filters });
  };

  const handlePrevPage = () => {
    if (page <= 1) return;
    const p = page - 1;
    setPage(p);
    loadGallery(p, filters);
    pushUrl({ q: searchText, page: p, filters });
  };

  const handleNextPage = () => {
    if (page >= totalPages) return;
    const p = page + 1;
    setPage(p);
    loadGallery(p, filters);
    pushUrl({ q: searchText, page: p, filters });
  };

  // ------------------------------------------------------------- render

  return (
    <div className="min-h-screen bg-firmato-bg">
      <Topbar
        onImport={() => setImportOpen(true)}
        onReset={handleClearAll}
        isUpdating={isUpdating}
      />

      <div className="flex items-stretch">
        {/* Left panel */}
        <div className="w-[38%] shrink-0 px-8 py-8 pr-4">
          <div className="bg-firmato-surface border border-firmato-border p-7 space-y-5">
            <SearchPanel
              searchText={searchText}
              onSearchChange={handleSearchChange}
              uploadedImage={uploadedImage}
              onImageUpload={handleImageUpload}
              onImageClear={handleImageClear}
              filters={filters}
              onFilterToggle={handleFilterToggle}
              onFilterRemove={handleFilterRemove}
              onFilterClearAll={handleFilterClearAll}
              onClearAll={handleClearAll}
              onSearchCommit={handleSearchCommit}
            />

            <div className="border-t border-firmato-border" />

            <div className="flex items-center justify-between">
              <span className="font-lato text-base font-medium text-firmato-text">
                Resultados
              </span>
              <span className="font-lato text-sm text-firmato-muted">
                {total} produtos
              </span>
            </div>

            <ProductGrid
              products={products}
              isLoading={isLoading || isSearching}
              onSelect={handleSelectProduct}
            />

            {!isInSearch && (
              <Pagination
                page={page}
                totalPages={totalPages}
                onPrev={handlePrevPage}
                onNext={handleNextPage}
              />
            )}
          </div>
        </div>

        {/* Right panel */}
        <div className="flex-1 px-4 py-8 pl-4 pr-8">
          <PreviewPanel
            selectedImage={selectedImage}
            selectedProduct={selectedProduct}
            loadingDetail={loadingDetail}
            similarProducts={similarProducts}
            onSelectSimilar={handleSelectSimilar}
          />
        </div>
      </div>

      <ImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onUpdatingChange={setIsUpdating}
      />
    </div>
  );
}