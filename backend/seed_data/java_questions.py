"""
A starter bank of 100 Java multiple-choice questions for the Recruiter mock-test
feature, seeded as a ready-to-use MockTestTemplate so recruiters have real content
on day one instead of an empty question list. HR Operations / Recruiters can add,
edit, or split these into more templates later via the Mock Tests tab or the
/api/mocktest/templates/<id>/questions endpoint — this file is just the initial
fill, not a permanent source of truth.

Each entry: (question_text, [options], correct_answer, topic)
"""

JAVA_QUESTIONS = [
    # --- Basics / Syntax (1-15) ---
    ("Which keyword is used to define a constant in Java?", ["const", "final", "static", "readonly"], "final", "Basics"),
    ("What is the default value of a boolean instance variable in Java?", ["true", "false", "0", "null"], "false", "Basics"),
    ("Which of these is not a Java primitive type?", ["int", "float", "String", "char"], "String", "Basics"),
    ("What is the size of an int in Java?", ["16 bits", "32 bits", "64 bits", "Platform-dependent"], "32 bits", "Basics"),
    ("Which operator is used to compare two values for equality in Java?", ["=", "==", "===", "eq"], "==", "Basics"),
    ("What does the 'static' keyword mean when applied to a method?", ["It belongs to the instance", "It belongs to the class, not an instance", "It cannot be overridden", "It runs only once ever"], "It belongs to the class, not an instance", "Basics"),
    ("Which of the following is the correct entry point signature for a Java application?", ["void main(String args[])", "public static void main(String[] args)", "public void main(String[] args)", "static void Main(String[] args)"], "public static void main(String[] args)", "Basics"),
    ("What is the result of 5 / 2 in Java, where both operands are int?", ["2.5", "2", "3", "2.0"], "2", "Basics"),
    ("Which keyword prevents a class from being subclassed?", ["static", "final", "private", "sealed"], "final", "Basics"),
    ("What is the default value of an uninitialized local variable in Java?", ["0", "null", "It must be initialized before use", "Depends on type"], "It must be initialized before use", "Basics"),
    ("Which of these is a valid way to declare an array of integers?", ["int arr[] = new int[5];", "int[] arr = new int(5);", "array int arr[5];", "int arr = new int[5]{};"], "int arr[] = new int[5];", "Basics"),
    ("What does the '++' operator do when placed before a variable (e.g. ++x)?", ["Increments after use", "Increments before use", "Decrements before use", "Has no effect"], "Increments before use", "Basics"),
    ("Which access modifier makes a member visible only within its own class?", ["public", "protected", "private", "default"], "private", "Basics"),
    ("What is the correct way to declare a multi-line comment in Java?", ["// comment", "/* comment */", "# comment", "<!-- comment -->"], "/* comment */", "Basics"),
    ("Which of these data types can hold the value 3.14 by default without a suffix?", ["float", "double", "int", "long"], "double", "Basics"),

    # --- OOP (16-35) ---
    ("What is method overriding in Java?", ["Defining multiple methods with the same name but different parameters", "Redefining a superclass method in a subclass with the same signature", "Declaring a method as static", "Hiding a variable in a subclass"], "Redefining a superclass method in a subclass with the same signature", "OOP"),
    ("What is method overloading in Java?", ["Multiple methods with the same name but different parameter lists in the same class", "Redefining a parent method in a child class", "Making a method final", "Calling a method recursively"], "Multiple methods with the same name but different parameter lists in the same class", "OOP"),
    ("Which keyword is used to inherit a class in Java?", ["implements", "extends", "inherits", "super"], "extends", "OOP"),
    ("Which keyword is used to implement an interface in Java?", ["extends", "implements", "interface", "inherits"], "implements", "OOP"),
    ("Can a Java class extend more than one class directly?", ["Yes, using commas", "No, Java supports single inheritance for classes", "Yes, using the 'multi' keyword", "Only abstract classes can"], "No, Java supports single inheritance for classes", "OOP"),
    ("Can a Java class implement more than one interface?", ["No, only one", "Yes, multiple interfaces can be implemented", "Only if they are abstract", "Only in Java 17+"], "Yes, multiple interfaces can be implemented", "OOP"),
    ("What is the purpose of the 'super' keyword?", ["To call a static method", "To refer to the parent class's members", "To create a new object", "To declare a constant"], "To refer to the parent class's members", "OOP"),
    ("What is an abstract class in Java?", ["A class that cannot have any methods", "A class that cannot be instantiated and may have abstract methods", "A class with only static methods", "A final class"], "A class that cannot be instantiated and may have abstract methods", "OOP"),
    ("Can an abstract class have a constructor?", ["No, never", "Yes, called when a subclass is instantiated", "Only if it has no abstract methods", "Only in interfaces"], "Yes, called when a subclass is instantiated", "OOP"),
    ("What is encapsulation?", ["Hiding implementation details and exposing only necessary parts", "Inheriting from multiple classes", "Overloading constructors", "Using static variables"], "Hiding implementation details and exposing only necessary parts", "OOP"),
    ("What is polymorphism in Java?", ["The ability of an object to take many forms", "Having multiple constructors", "Declaring multiple classes in one file", "Using the 'this' keyword"], "The ability of an object to take many forms", "OOP"),
    ("What does the 'this' keyword refer to?", ["The parent class", "The current instance of the class", "A static context", "The next object created"], "The current instance of the class", "OOP"),
    ("Since which Java version can interfaces have default methods with a body?", ["Java 6", "Java 7", "Java 8", "Java 11"], "Java 8", "OOP"),
    ("What is a constructor in Java?", ["A method that returns an object", "A special method used to initialize objects, with no return type", "A static utility method", "An abstract method"], "A special method used to initialize objects, with no return type", "OOP"),
    ("What happens if a class does not define any constructor?", ["Compilation fails", "The compiler provides a default no-arg constructor", "The class cannot be instantiated", "It inherits the parent's constructor automatically"], "The compiler provides a default no-arg constructor", "OOP"),
    ("What is the output of calling toString() on an object that hasn't overridden it?", ["null", "An empty string", "ClassName@hashcode representation", "A compile error"], "ClassName@hashcode representation", "OOP"),
    ("Which method must be overridden alongside equals() to maintain the general contract?", ["toString()", "hashCode()", "clone()", "finalize()"], "hashCode()", "OOP"),
    ("What is a marker interface? Give an example.", ["An interface with only default methods", "An empty interface used to signal metadata, e.g. Serializable", "An interface that must be implemented first", "A deprecated interface type"], "An empty interface used to signal metadata, e.g. Serializable", "OOP"),
    ("Can a static method be overridden in Java?", ["Yes, normally", "No — it can be hidden but not overridden (no runtime polymorphism)", "Only if declared final", "Only in interfaces"], "No — it can be hidden but not overridden (no runtime polymorphism)", "OOP"),
    ("What is composition in object-oriented design?", ["Building a class using instances of other classes rather than inheriting", "Overriding multiple methods", "Using static blocks", "Declaring multiple interfaces"], "Building a class using instances of other classes rather than inheriting", "OOP"),

    # --- Collections (36-50) ---
    ("Which interface is the root of the Java Collections hierarchy (excluding Map)?", ["List", "Collection", "Set", "Iterable"], "Collection", "Collections"),
    ("Which List implementation provides fast random access but slow insertion in the middle?", ["LinkedList", "ArrayList", "Vector", "Stack"], "ArrayList", "Collections"),
    ("Which List implementation is best suited for frequent insertions/deletions at both ends?", ["ArrayList", "LinkedList", "Vector", "CopyOnWriteArrayList"], "LinkedList", "Collections"),
    ("Does a HashSet allow duplicate elements?", ["Yes", "No", "Only one duplicate", "Depends on capacity"], "No", "Collections"),
    ("Which Set implementation maintains elements in sorted order?", ["HashSet", "LinkedHashSet", "TreeSet", "EnumSet"], "TreeSet", "Collections"),
    ("Which Map implementation does not guarantee any iteration order?", ["LinkedHashMap", "TreeMap", "HashMap", "EnumMap"], "HashMap", "Collections"),
    ("Which Map implementation maintains insertion order?", ["HashMap", "TreeMap", "LinkedHashMap", "ConcurrentHashMap"], "LinkedHashMap", "Collections"),
    ("What does HashMap use internally to resolve key collisions (Java 8+)?", ["A secondary HashMap", "A linked list, converting to a red-black tree when a bucket grows large", "It doesn't allow collisions", "A separate array"], "A linked list, converting to a red-black tree when a bucket grows large", "Collections"),
    ("Which interface does ArrayList implement that allows it to be used in a for-each loop?", ["Comparable", "Iterable", "Cloneable", "Serializable"], "Iterable", "Collections"),
    ("What is the time complexity of get(index) on an ArrayList?", ["O(n)", "O(1)", "O(log n)", "O(n^2)"], "O(1)", "Collections"),
    ("What is the time complexity of get(index) on a LinkedList?", ["O(1)", "O(n)", "O(log n)", "O(n log n)"], "O(n)", "Collections"),
    ("Which collection class is thread-safe by default (legacy)?", ["ArrayList", "HashMap", "Vector", "HashSet"], "Vector", "Collections"),
    ("What does Collections.unmodifiableList() do?", ["Sorts the list", "Returns a read-only view of the list", "Creates a deep copy", "Removes duplicates"], "Returns a read-only view of the list", "Collections"),
    ("Which interface must an object implement to be used as a key in a TreeMap without a custom Comparator?", ["Serializable", "Comparable", "Cloneable", "Iterable"], "Comparable", "Collections"),
    ("What is the difference between Comparable and Comparator?", ["No difference", "Comparable defines natural ordering within the class; Comparator defines external, custom ordering", "Comparator is faster", "Comparable is deprecated"], "Comparable defines natural ordering within the class; Comparator defines external, custom ordering", "Collections"),

    # --- Exceptions (51-60) ---
    ("Which class is the superclass of all exceptions and errors in Java?", ["Exception", "RuntimeException", "Throwable", "Error"], "Throwable", "Exceptions"),
    ("What is the difference between checked and unchecked exceptions?", ["No difference", "Checked exceptions must be declared or caught at compile time; unchecked ones need not be", "Unchecked exceptions are more severe", "Checked exceptions only occur in I/O"], "Checked exceptions must be declared or caught at compile time; unchecked ones need not be", "Exceptions"),
    ("Which block always executes, whether or not an exception is thrown?", ["catch", "finally", "try", "throw"], "finally", "Exceptions"),
    ("What keyword is used to manually throw an exception?", ["throw", "throws", "raise", "catch"], "throw", "Exceptions"),
    ("What keyword declares that a method might throw a checked exception?", ["throw", "throws", "catch", "try"], "throws", "Exceptions"),
    ("Is NullPointerException a checked or unchecked exception?", ["Checked", "Unchecked", "Neither — it's an Error", "Depends on the JVM"], "Unchecked", "Exceptions"),
    ("What is a try-with-resources statement used for?", ["Catching multiple exceptions in one block", "Automatically closing resources like streams that implement AutoCloseable", "Declaring static resources", "Retrying a failed operation"], "Automatically closing resources like streams that implement AutoCloseable", "Exceptions"),
    ("Can a single try block have multiple catch blocks?", ["No", "Yes, to handle different exception types differently", "Only two maximum", "Only for checked exceptions"], "Yes, to handle different exception types differently", "Exceptions"),
    ("What happens if an exception is thrown inside a finally block?", ["It is ignored", "It can suppress or replace any exception from the try block", "The program terminates immediately without any handling", "It is automatically logged"], "It can suppress or replace any exception from the try block", "Exceptions"),
    ("Which of these is a custom/user-defined exception typically expected to extend?", ["Throwable directly", "Exception or RuntimeException", "Error", "Object"], "Exception or RuntimeException", "Exceptions"),

    # --- Multithreading / Concurrency (61-70) ---
    ("Which interface represents a task that can be executed by a thread and returns no result?", ["Callable", "Runnable", "Future", "Executor"], "Runnable", "Concurrency"),
    ("Which interface allows a task to return a result and throw a checked exception?", ["Runnable", "Callable", "Thread", "Executor"], "Callable", "Concurrency"),
    ("What does the 'synchronized' keyword do?", ["Speeds up method execution", "Ensures only one thread can execute the block/method on a given object at a time", "Marks a method as thread-unsafe", "Creates a new thread"], "Ensures only one thread can execute the block/method on a given object at a time", "Concurrency"),
    ("What is a race condition?", ["A performance benchmark", "A bug where the outcome depends on the unpredictable timing of multiple threads", "A type of deadlock", "A compiler optimization"], "A bug where the outcome depends on the unpredictable timing of multiple threads", "Concurrency"),
    ("What is a deadlock?", ["A thread running forever with no output", "Two or more threads waiting on each other indefinitely for resources", "A thread that has finished execution", "An exception during thread creation"], "Two or more threads waiting on each other indefinitely for resources", "Concurrency"),
    ("Which method starts a new thread of execution (not just runs code on the current thread)?", ["run()", "start()", "execute()", "init()"], "start()", "Concurrency"),
    ("What does calling thread.join() do?", ["Kills the thread", "Makes the calling thread wait until the target thread finishes", "Starts the thread", "Pauses all threads"], "Makes the calling thread wait until the target thread finishes", "Concurrency"),
    ("What is the purpose of the volatile keyword?", ["Makes a variable immutable", "Ensures visibility of changes to a variable across threads", "Improves performance of loops", "Declares a constant"], "Ensures visibility of changes to a variable across threads", "Concurrency"),
    ("Which package provides higher-level concurrency utilities like ExecutorService and thread pools?", ["java.lang", "java.util.concurrent", "java.io", "java.thread"], "java.util.concurrent", "Concurrency"),
    ("What does ExecutorService.shutdown() do?", ["Immediately kills all running tasks", "Initiates an orderly shutdown, letting submitted tasks finish first", "Pauses the executor temporarily", "Restarts the thread pool"], "Initiates an orderly shutdown, letting submitted tasks finish first", "Concurrency"),

    # --- Strings (71-80) ---
    ("Are Java Strings mutable or immutable?", ["Mutable", "Immutable", "Mutable only inside a method", "Depends on the JVM"], "Immutable", "Strings"),
    ("Which class should be used for efficient string concatenation in a loop?", ["String", "StringBuilder", "StringBuffer only", "CharSequence"], "StringBuilder", "Strings"),
    ("What is the key difference between StringBuilder and StringBuffer?", ["No difference", "StringBuffer is synchronized (thread-safe); StringBuilder is not", "StringBuilder is immutable", "StringBuffer is deprecated"], "StringBuffer is synchronized (thread-safe); StringBuilder is not", "Strings"),
    ("What does the String Pool (intern pool) do?", ["Stores compiled bytecode", "Reuses identical string literals to save memory", "Encrypts strings", "Caches exceptions"], "Reuses identical string literals to save memory", "Strings"),
    ("Does '==' compare String contents or references by default?", ["Contents", "References (unless both are pooled literals)", "Always contents in Java", "It causes a compile error"], "References (unless both are pooled literals)", "Strings"),
    ("Which method correctly compares the actual content of two String objects?", ["==", ".equals()", ".compareTo() only", "hashCode()"], ".equals()", "Strings"),
    ("What does \"Hello\".charAt(1) return?", ["'H'", "'e'", "'l'", "An error"], "'e'", "Strings"),
    ("What does \"  Java  \".trim() return?", ["\"  Java  \"", "\"Java\"", "\"Java  \"", "An exception"], "\"Java\"", "Strings"),
    ("Which method splits a String based on a regular expression?", ["split()", "divide()", "tokenize()", "partition()"], "split()", "Strings"),
    ("What does \"abc\".substring(1) return?", ["\"a\"", "\"bc\"", "\"ab\"", "\"abc\""], "\"bc\"", "Strings"),

    # --- Generics (81-85) ---
    ("What is the main benefit of using generics in Java?", ["Faster runtime execution", "Compile-time type safety, avoiding ClassCastException at runtime", "Smaller bytecode size", "Automatic thread safety"], "Compile-time type safety, avoiding ClassCastException at runtime", "Generics"),
    ("What does the wildcard '?' represent in generics, e.g. List<?>", ["Any single specific type, unknown at compile time", "A null value", "An error", "A checked exception"], "Any single specific type, unknown at compile time", "Generics"),
    ("What does 'List<? extends Number>' mean?", ["A list that can hold any object", "A list of Number or any of its subclasses (read-only in practice)", "A list of exactly Number type only", "A syntax error"], "A list of Number or any of its subclasses (read-only in practice)", "Generics"),
    ("What is type erasure in Java generics?", ["Generics are removed at compile time and replaced with raw types/casts at bytecode level", "Generics are erased at runtime causing errors", "A feature to delete unused types", "A garbage collection strategy"], "Generics are removed at compile time and replaced with raw types/casts at bytecode level", "Generics"),
    ("Can you create a generic array directly in Java, e.g. new T[10]?", ["Yes, always", "No, due to type erasure this isn't directly allowed", "Only for primitive types", "Only in Java 17+"], "No, due to type erasure this isn't directly allowed", "Generics"),

    # --- JVM / Memory (86-95) ---
    ("What does JVM stand for?", ["Java Verified Method", "Java Virtual Machine", "Java Variable Manager", "Java Validation Module"], "Java Virtual Machine", "JVM"),
    ("Which part of memory stores objects created with 'new'?", ["Stack", "Heap", "Method Area", "Register"], "Heap", "JVM"),
    ("Which part of memory stores local variables and method call frames?", ["Heap", "Stack", "Metaspace", "Constant Pool"], "Stack", "JVM"),
    ("What is the primary role of the Garbage Collector?", ["Compiling Java code", "Automatically reclaiming memory occupied by unreachable objects", "Managing thread priorities", "Optimizing loops"], "Automatically reclaiming memory occupied by unreachable objects", "JVM"),
    ("What replaced PermGen space starting in Java 8?", ["Heap", "Metaspace", "Stack", "Code Cache"], "Metaspace", "JVM"),
    ("What is JIT compilation?", ["Just-In-Time compilation of bytecode to native machine code at runtime for performance", "A tool for debugging", "A build tool", "A memory leak detector"], "Just-In-Time compilation of bytecode to native machine code at runtime for performance", "JVM"),
    ("What is a ClassLoader responsible for?", ["Compiling .java files", "Loading class bytecode into the JVM at runtime", "Managing threads", "Formatting output"], "Loading class bytecode into the JVM at runtime", "JVM"),
    ("What causes a StackOverflowError?", ["Running out of heap memory", "Excessive or infinite recursion exhausting the call stack", "Too many classes loaded", "A network timeout"], "Excessive or infinite recursion exhausting the call stack", "JVM"),
    ("What causes an OutOfMemoryError on the heap?", ["Too many method calls", "The application creates more objects than the heap can hold and they can't be collected", "A missing semicolon", "A finally block"], "The application creates more objects than the heap can hold and they can't be collected", "JVM"),
    ("What is the purpose of the 'finalize()' method (now deprecated)?", ["Called before an object is garbage collected, for cleanup", "Marks a class as final", "Ends the main method", "Closes all open threads"], "Called before an object is garbage collected, for cleanup", "JVM"),

    # --- Java 8+ / Misc (96-100) ---
    ("What is a lambda expression in Java?", ["A shorthand syntax for implementing a functional interface", "A type of exception", "A deprecated feature", "A memory management tool"], "A shorthand syntax for implementing a functional interface", "Java 8+"),
    ("What is a functional interface?", ["An interface with any number of methods", "An interface with exactly one abstract method, usable as a lambda target", "A class with only static methods", "An interface that cannot be implemented"], "An interface with exactly one abstract method, usable as a lambda target", "Java 8+"),
    ("What does the Stream API's filter() method do?", ["Sorts elements", "Selects elements matching a given predicate", "Removes duplicates only", "Converts types"], "Selects elements matching a given predicate", "Java 8+"),
    ("What does Optional<T> help avoid?", ["ArrayIndexOutOfBoundsException", "NullPointerException, by explicitly modeling the presence or absence of a value", "ClassCastException", "Compilation errors"], "NullPointerException, by explicitly modeling the presence or absence of a value", "Java 8+"),
    ("Which Java 8 feature allows adding new methods to interfaces without breaking existing implementations?", ["Static imports", "Default methods", "Generics", "Annotations"], "Default methods", "Java 8+"),
]

assert len(JAVA_QUESTIONS) == 100, f"Expected 100 questions, found {len(JAVA_QUESTIONS)}"
