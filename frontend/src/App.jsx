import { useEffect, useState } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_BASE || 'http://localhost:5000'

export default function App() {
  const [applications, setApplications] = useState([])
  const [metrics, setMetrics]           = useState({ total_applications: 0, by_status: {} })
  const [uploading, setUploading]       = useState(false)
  const [filter, setFilter]             = useState('')

  async function load() {
    const params = filter ? { status: filter } : {}
    const [appsRes, metricsRes] = await Promise.all([
      axios.get(`${API}/api/applications`, { params }),
      axios.get(`${API}/api/metrics`),
    ])
    setApplications(appsRes.data.applications || [])
    setMetrics(metricsRes.data)
  }

  useEffect(() => { load() }, [filter])

  async function handleUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    try {
      const { data } = await axios.post(`${API}/api/applications/upload-url`, { filename: file.name })
      await axios.put(data.upload_url, file, { headers: { 'Content-Type': 'application/pdf' } })
      alert(`Uploaded! ID: ${data.application_id}`)
      load()
    } catch (err) {
      alert('Upload failed: ' + err.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function updateStatus(id, status) {
    await axios.patch(`${API}/api/applications/${id}/status`, { status })
    load()
  }

  return (
    <div className="app">
      <header>
        <h1>CreditFlow</h1>
        <p>Trade credit operations dashboard</p>
      </header>

      <section className="metrics">
        <div className="metric-card">
          <div className="metric-value">{metrics.total_applications}</div>
          <div className="metric-label">Total applications</div>
        </div>
        {Object.entries(metrics.by_status).map(([s, n]) => (
          <div className="metric-card" key={s}>
            <div className="metric-value">{n}</div>
            <div className="metric-label">{s.replace(/_/g, ' ')}</div>
          </div>
        ))}
      </section>

      <section className="actions">
        <label className="btn">
          {uploading ? 'Uploading...' : '+ Upload application PDF'}
          <input type="file" accept="application/pdf" onChange={handleUpload} disabled={uploading} hidden />
        </label>
        <select value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="uploading">Uploading</option>
          <option value="pending_review">Pending review</option>
          <option value="in_review">In review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </section>

      <table>
        <thead>
          <tr><th>ID</th><th>Applicant</th><th>Credit requested</th><th>Status</th><th>Created</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {applications.map(a => (
            <tr key={a.application_id}>
              <td className="mono">{a.application_id.slice(0, 8)}</td>
              <td>{a.extracted_fields?.applicant_name || '—'}</td>
              <td>{a.extracted_fields?.requested_credit_limit || '—'}</td>
              <td><span className={`status status-${a.status}`}>{a.status?.replace(/_/g,' ')}</span></td>
              <td>{new Date(a.created_at).toLocaleString()}</td>
              <td>
                {a.status === 'pending_review' && <button onClick={() => updateStatus(a.application_id, 'in_review')}>Start review</button>}
                {a.status === 'in_review' && <>
                  <button onClick={() => updateStatus(a.application_id, 'approved')}>Approve</button>
                  <button onClick={() => updateStatus(a.application_id, 'rejected')}>Reject</button>
                </>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {applications.length === 0 && <p className="empty">No applications yet. Upload a PDF to get started.</p>}
    </div>
  )
}
