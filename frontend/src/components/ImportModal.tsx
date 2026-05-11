"use client";
import { useState } from "react";
import { CheckCircle, FileText, AlertTriangle, RefreshCw, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import type { UploadStats } from "@/types";

interface ImportModalProps {
  open: boolean;
  onClose: () => void;
  onUpdatingChange?: (updating: boolean) => void;
}

type ResultState =
  | { kind: "idle" }
  | { kind: "success"; stats: UploadStats; elapsed: number }
  | { kind: "error"; message: string };

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-firmato-border last:border-b-0">
      <span className="font-lato text-sm text-firmato-muted">{label}</span>
      <span
        className={`font-lato text-sm font-semibold ${
          value > 0 ? "text-firmato-accent" : "text-firmato-text"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

export function ImportModal({ open, onClose, onUpdatingChange }: ImportModalProps) {
  const [result, setResult] = useState<ResultState>({ kind: "idle" });

  const handleClose = () => {
    setResult({ kind: "idle" });
    onClose();
  };

  const downloadLog = () => {
    window.open("/api/catalog/latest-log", "_blank");
  };

  // Confirmation step: user clicks "Confirmar" → closes modal, loading starts in background
  const handleConfirm = () => {
    onClose(); // close the confirm modal immediately — user can navigate freely
    startUpdate();
  };

  const startUpdate = async () => {
    onUpdatingChange?.(true);

    try {
      const res = await fetch("/api/catalog/register", {
        method: "POST",
      });

      const text = await res.text();

      let data: any = null;

      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        throw new Error(text || `Erro HTTP ${res.status}`);
      }

      if (!res.ok || data?.detail) {
        setResult({
          kind: "error",
          message: data?.detail ?? `Erro HTTP ${res.status}`,
        });
        return;
      }

      setResult({
        kind: "success",
        stats: data,
        elapsed: data.elapsed_seconds ?? 0,
      });
    } catch (e) {
      setResult({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    } finally {
      onUpdatingChange?.(false);
    }
  };

  // If result modal should auto-open when done
  const resultOpen = result.kind === "success" || result.kind === "error";

  return (
    <>
      {/* ── Confirmation modal ── */}
      <Modal open={open && result.kind === "idle"} onClose={handleClose} title="Atualizar Catálogo">
        <div className="space-y-5">
          <p className="font-lato text-sm text-firmato-muted leading-relaxed">
            Deseja sincronizar o catálogo com o SharePoint, processar imagens novas
            ou alteradas e retreinar os embeddings de busca?
          </p>
          <p className="font-lato text-xs text-firmato-muted/70 leading-relaxed border-l-2 border-firmato-accent/40 pl-3">
            O processamento ocorre em segundo plano — você pode continuar
            navegando normalmente enquanto aguarda o resultado.
          </p>
          <div className="flex gap-3 pt-1">
            <Button variant="outline" className="flex-1" onClick={handleClose}>
              Cancelar
            </Button>
            <Button variant="solid" className="flex-1" onClick={handleConfirm}>
              <RefreshCw size={14} />
              Confirmar
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── Result modal (success / error) — opens automatically when done ── */}
      <Modal open={resultOpen} onClose={handleClose} title={
        result.kind === "success" ? "Atualização Concluída" : "Falha na Atualização"
      }>
        {result.kind === "success" && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <CheckCircle size={20} className="text-green-500 shrink-0" />
              <div>
                <p className="font-lato text-[15px] font-semibold text-firmato-text">
                  Catálogo atualizado com sucesso
                </p>
                <p className="font-lato text-xs text-firmato-muted">
                  {result.elapsed.toFixed(1)}s · embeddings recarregados
                </p>
              </div>
            </div>

            <div className="border-t border-firmato-border" />

            <div className="bg-firmato-bg p-4 space-y-0">
              <p className="font-lato text-[10px] font-bold text-firmato-accent uppercase tracking-widest mb-2">
                Resumo
              </p>
              <StatRow label="Produtos processados" value={result.stats.processed ?? 0} />
              <StatRow label="Ignorados (sem alteração)" value={result.stats.skipped ?? 0} />
              <StatRow label="Erros" value={result.stats.errors ?? 0} />
              {result.stats.updated_ids && (
                <div className="flex items-center justify-between py-1.5">
                  <span className="font-lato text-sm text-firmato-muted">IDs atualizados</span>
                  <span className="font-lato text-sm font-semibold text-firmato-text">
                    {Array.isArray(result.stats.updated_ids) ? result.stats.updated_ids.length : 0}
                  </span>
                </div>
              )}
            </div>

            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={downloadLog}>
                <FileText size={14} />
                Baixar Log
              </Button>
              <Button variant="solid" className="flex-1" onClick={handleClose}>
                Fechar
              </Button>
            </div>
          </div>
        )}

        {result.kind === "error" && (
          <div className="space-y-4">
            <div className="flex items-start gap-2">
              <AlertTriangle size={20} className="text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="font-lato text-[15px] font-semibold text-firmato-text">
                  Falha na atualização
                </p>
                <p className="font-lato text-xs text-firmato-muted mt-1 leading-relaxed">
                  {result.message}
                </p>
              </div>
            </div>
            <div className="flex gap-3 pt-1">
              <Button variant="outline" className="flex-1" onClick={handleClose}>
                Fechar
              </Button>
              <Button variant="solid" className="flex-1" onClick={downloadLog}>
                <FileText size={14} />
                Ver Log
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}