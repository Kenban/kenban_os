const WebSocket = require('ws')
const redis = require('redis')

const server = new WebSocket.Server({ port : 8000 });
let sockets = []

server.on('connection', function connection(ws) {
    sockets.push(ws);

    // Subscribe to redis when a websocket connects
    let redisClient = redis.createClient("redis://localhost:6379")
    redisClient.connect()
    redisClient.subscribe('banner_message', (message) => {
        ws.send(message)
    })

    // Unsubscribe when the websocket closes
    ws.on('close', function close() {
        sockets = sockets.filter(s => s !== ws)
        redisClient.unsubscribe('banner_message')
    })
})

console.log("WebSocket server started")
