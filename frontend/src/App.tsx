import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type { Item, WhoAmI } from "./api";
import "./App.css";

const errorMessage = (e: unknown) =>
  e instanceof Error ? e.message : "Erro inesperado";

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // qual container respondeu (para ver o balanceamento)
  const [last, setLast] = useState<WhoAmI | null>(null);
  const [tally, setTally] = useState<
    Record<string, { info: WhoAmI; count: number }>
  >({});

  // formulário de criação
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  // edição inline
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api.list());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // executa uma ação e recarrega a lista
  const run = async (action: () => Promise<unknown>) => {
    try {
      setError(null);
      await action();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const handleCreate = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    run(async () => {
      await api.create({ name: name.trim(), description: description.trim() });
      setName("");
      setDescription("");
    });
  };

  const checkContainer = async () => {
    try {
      setError(null);
      const info = await api.whoami();
      setLast(info);
      setTally((prev) => ({
        ...prev,
        [info.instance_id]: {
          info,
          count: (prev[info.instance_id]?.count ?? 0) + 1,
        },
      }));
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const startEdit = (item: Item) => {
    setEditingId(item.id);
    setEditName(item.name);
    setEditDescription(item.description);
  };

  const saveEdit = (id: string) => {
    if (!editName.trim()) {
      setError("O nome não pode ficar vazio");
      return;
    }
    run(async () => {
      await api.update(id, {
        name: editName.trim(),
        description: editDescription.trim(),
      });
      setEditingId(null);
    });
  };

  const toggleDone = (item: Item) =>
    run(() => api.update(item.id, { done: !item.done }));

  const handleDelete = (item: Item) => {
    if (!window.confirm(`Excluir "${item.name}"?`)) return;
    run(() => api.remove(item.id));
  };

  return (
    <main className="container">
      <h1>Lab App</h1>

      <section className="card whoami">
        <button onClick={checkContainer}>Qual servidor está respondendo?</button>
        {last && (
          <>
            <p>
              Respondeu agora: IP <code>{last.ip}</code> · zona{" "}
              <code>{last.zone}</code> · container <code>{last.container}</code>
            </p>
            <ul>
              {Object.values(tally).map(({ info, count }) => (
                <li key={info.instance_id}>
                  <code>{info.ip}</code> ({info.zone}, {info.instance_id}):{" "}
                  {count} {count === 1 ? "vez" : "vezes"}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <form className="card form" onSubmit={handleCreate}>
        <input
          placeholder="Nome"
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          placeholder="Descrição (opcional)"
          value={description}
          maxLength={500}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button type="submit" disabled={!name.trim()}>
          Adicionar
        </button>
      </form>


      {error && <p className="error">{error}</p>}
      {loading && <p>Carregando…</p>}
      {!loading && items.length === 0 && !error && (
        <p className="muted">Nenhum item por aqui.</p>
      )}

      <ul className="list">
        {items.map((item) => (
          <li key={item.id} className={`card item ${item.done ? "done" : ""}`}>
            {editingId === item.id ? (
              <div className="edit">
                <input
                  value={editName}
                  maxLength={100}
                  onChange={(e) => setEditName(e.target.value)}
                />
                <input
                  value={editDescription}
                  maxLength={500}
                  onChange={(e) => setEditDescription(e.target.value)}
                />
                <div className="actions">
                  <button onClick={() => saveEdit(item.id)}>Salvar</button>
                  <button className="ghost" onClick={() => setEditingId(null)}>
                    Cancelar
                  </button>
                </div>
              </div>
            ) : (
              <>
                <input
                  type="checkbox"
                  checked={item.done}
                  onChange={() => toggleDone(item)}
                  aria-label="Concluído"
                />
                <div className="content">
                  <strong>{item.name}</strong>
                  {item.description && <p>{item.description}</p>}
                  <small className="muted">
                    Criado em {new Date(item.created_at).toLocaleString("pt-BR")}
                  </small>
                </div>
                <div className="actions">
                  <button className="ghost" onClick={() => startEdit(item)}>
                    Editar
                  </button>
                  <button className="danger" onClick={() => handleDelete(item)}>
                    Excluir
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
