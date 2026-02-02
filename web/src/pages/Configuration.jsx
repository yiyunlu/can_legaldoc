import React, { useEffect, useState } from 'react';
import { api } from '../api';

function Configuration() {
    const [targets, setTargets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [newTarget, setNewTarget] = useState({
        name: '',
        province: '',
        type: 'Statutes',
        url: ''
    });

    const [deletingIndex, setDeletingIndex] = useState(null);

    const fetchConfig = async () => {
        try {
            const data = await api.getConfig();
            setTargets(data.targets);
        } catch (error) {
            console.error("Failed to fetch config", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchConfig();
    }, []);

    const handleAddTarget = async (e) => {
        e.preventDefault();
        const updated = [...targets, newTarget];
        try {
            await api.updateConfig(updated);
            setTargets(updated);
            setNewTarget({ name: '', province: '', type: 'Statutes', url: '' });
        } catch (err) {
            alert("Failed to save config");
        }
    };

    const confirmRemove = async (index) => {
        const updated = targets.filter((_, i) => i !== index);
        try {
            await api.updateConfig(updated);
            setTargets(updated);
            setDeletingIndex(null);
        } catch (err) {
            alert("Failed to save config");
        }
    };

    if (loading) return <div>Loading...</div>;

    return (
        <div>
            <div style={{ marginBottom: '20px', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px' }}>
                <h3 style={{ margin: '0 0 10px 0' }}>Add Target</h3>
                <form onSubmit={handleAddTarget} style={{ display: 'flex', gap: '10px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '11px' }}>Name</label>
                        <input className="input" style={{ width: '150px' }} value={newTarget.name} onChange={e => setNewTarget({ ...newTarget, name: e.target.value })} required />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '11px' }}>Province</label>
                        <input className="input" style={{ width: '60px' }} value={newTarget.province} onChange={e => setNewTarget({ ...newTarget, province: e.target.value })} required />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '11px' }}>Type</label>
                        <select className="input" value={newTarget.type} onChange={e => setNewTarget({ ...newTarget, type: e.target.value })}>
                            <option value="Statutes">Statutes</option>
                            <option value="Regulations">Regulations</option>
                            <option value="Courts">Courts</option>
                            <option value="Boards and Tribunals">Boards and Tribunals</option>
                        </select>
                    </div>
                    <div style={{ flexGrow: 1 }}>
                        <label style={{ display: 'block', fontSize: '11px' }}>URL</label>
                        <input className="input" style={{ width: '100%' }} value={newTarget.url} onChange={e => setNewTarget({ ...newTarget, url: e.target.value })} required />
                    </div>
                    <button type="submit">Add</button>
                </form>
            </div>

            <div>
                <h3 style={{ margin: '0 0 10px 0' }}>Configured Targets</h3>
                <table className="dense-table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Province</th>
                            <th>Type</th>
                            <th>URL</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {targets.map((t, i) => (
                            <tr key={i}>
                                <td>{t.name}</td>
                                <td>{t.province}</td>
                                <td>{t.type}</td>
                                <td style={{ maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    <a href={t.url} target="_blank" style={{ color: 'var(--link-color)' }}>{t.url}</a>
                                </td>
                                <td>
                                    {deletingIndex === i ? (
                                        <>
                                            <span className="action-link" onClick={() => confirmRemove(i)} style={{ color: 'var(--error)', fontWeight: 'bold' }}>Sure?</span>
                                            <span className="action-link" onClick={() => setDeletingIndex(null)} style={{ color: 'gray' }}>Cancel</span>
                                        </>
                                    ) : (
                                        <span className="action-link" onClick={() => setDeletingIndex(i)} style={{ color: 'var(--error)' }}>Remove</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export default Configuration;
