import { CircularProgress } from '@mui/material'

function Loading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
      <CircularProgress />
    </div>
  )
}

export default Loading