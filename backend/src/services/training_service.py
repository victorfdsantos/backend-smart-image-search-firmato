"""
TrainingService — cliente HTTP que chama o AI Service para retreinamento.

Usa asyncio.to_thread para não bloquear o event loop do FastAPI, já que
requests é síncrono.
"""

import asyncio
import logging

import requests


class TrainingService:

    _AI_URL     = "http://ai:9000/training"
    _TIMEOUT    = 600  # segundos — o treino pode demorar

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    # ------------------------------------------------------------------
    # PUBLIC (async — deve ser chamado com await)
    # ------------------------------------------------------------------

    async def train(self, image_ids: list[str], data_ids: list[str]) -> bool:
        """
        Chama POST /training no AI Service de forma assíncrona.
        Retorna True em sucesso, False em qualquer falha.
        """
        self.logger.info(
            f"[Training] Iniciando | image_ids={len(image_ids)} | data_ids={len(data_ids)}"
        )
        return await asyncio.to_thread(self._post, image_ids, data_ids)

    # ------------------------------------------------------------------
    # INTERNAL (síncrono — roda em thread pool via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _post(self, image_ids: list[str], data_ids: list[str]) -> bool:
        try:
            resp = requests.post(
                self._AI_URL,
                json={
                    "image_ids": image_ids,
                    "data_ids":  data_ids,
                },
                timeout=self._TIMEOUT,
            )

            if resp.status_code == 200:
                data    = resp.json()
                status  = data.get("status", "unknown")
                errors  = data.get("errors", [])
                elapsed = data.get("elapsed", "?")

                if errors:
                    self.logger.warning(
                        f"[Training] Concluído com erros parciais | "
                        f"status={status} elapsed={elapsed}s errors={errors}"
                    )
                else:
                    self.logger.info(
                        f"[Training] OK | status={status} elapsed={elapsed}s"
                    )

                # "partial" ainda é sucesso — alguns IDs podem ter falhado
                # por imagem ausente, mas os demais foram indexados
                return True

            self.logger.warning(
                f"[Training] Resposta inesperada | "
                f"status_code={resp.status_code} body={resp.text[:300]}"
            )
            return False

        except requests.exceptions.Timeout:
            self.logger.error(
                f"[Training] Timeout após {self._TIMEOUT}s — AI Service demorou demais"
            )
            return False

        except Exception as exc:
            self.logger.error(f"[Training] Erro inesperado: {exc}", exc_info=True)
            return False