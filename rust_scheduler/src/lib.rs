pub struct RequestQueue{
    pending_requests: VecDeque<Request>,
}

impl RequestQueue {
    // Creates a new RequestQueue
    pub fn new() -> self {
        todo!()
    }
    // Adds a request to the queue (back of the queue)
    // Borrows mutable reference to self so that the queue can be modified, and moves request into the queue 
    pub fn enqueue(&mut self, request: Request) {
        todo!()
    }
    // Removes the oldest request 
    // Returns None if the queue is empty (via the Option type)
    pub fn dequeue(&mut self) -> Option<Request> {
        todo!()
    }
    // Returns the number of requests in the queue
    pub fn len(&mut self) -> usize {
        todo!()
    }
}

// Add a test module to test the RequestQueue implementation
